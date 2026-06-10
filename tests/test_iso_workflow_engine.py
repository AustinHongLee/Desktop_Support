from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_workflow, topological_order, validate_graph
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES, WRITES_CSV, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.registry import NodeRegistry
from launcher.plugins.iso_tools.workflow.schema import NodeSpec, PortSpec, normalize_graph


class EchoNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.echo",
        display_name="Echo",
        description="Echo a value.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        params_schema={"mode": {"type": "text", "enum": ["copy"], "default": "copy"}},
    )

    def run(self, ctx):
        return {"value": ctx.inputs["value"]}


class EffectNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.effect",
        display_name="Effect",
        description="Auto side-effect fake node.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        side_effects=(WRITES_CSV,),
    )

    def run(self, ctx):
        decision = ctx.request_side_effect(WRITES_CSV, {"path": "fake.csv"})
        if decision != "executed":
            ctx.mark_blocked(decision)
        return {"value": decision}


class GuardedNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.guarded",
        display_name="Guarded",
        description="Guarded fake node.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        side_effects=(RENAMES_FILES,),
        guarded=True,
        requires_confirm_default=True,
    )

    def run(self, ctx):
        decision = ctx.request_side_effect(RENAMES_FILES, {"count": 1})
        if decision != "executed":
            ctx.mark_blocked(decision)
        return {"value": decision}


class MissingDecisionNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.missing_decision",
        display_name="Missing decision",
        description="Declares an effect but does not request it.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        side_effects=(WRITES_CSV,),
    )

    def run(self, ctx):
        return {"value": ctx.inputs["value"]}


class IsoWorkflowEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry()
        self.registry.register(EchoNode)
        self.registry.register(EffectNode)
        self.registry.register(GuardedNode)
        self.registry.register(MissingDecisionNode)

    def test_refs_infer_edges_and_topological_order_is_deterministic(self) -> None:
        graph = _graph(
            [
                {"node_id": "b", "node_type": "test.echo", "inputs": {"value": "$nodes.a.outputs.value"}},
                {"node_id": "a", "node_type": "test.echo", "inputs": {"value": "$workflow.inputs.seed"}},
            ],
            inputs={"seed": "ok"},
        )

        self.assertEqual([edge.label() for edge in graph.edges], ["a.value->b.value"])
        self.assertEqual(topological_order(graph), ["a", "b"])
        self.assertFalse([issue for issue in validate_graph(graph, self.registry) if issue.severity == "error"])

    def test_declared_edges_must_match_refs(self) -> None:
        graph = _graph(
            [
                {"node_id": "a", "node_type": "test.echo", "inputs": {"value": "$workflow.inputs.seed"}},
                {"node_id": "b", "node_type": "test.echo", "inputs": {"value": "$nodes.a.outputs.value"}},
            ],
            inputs={"seed": "ok"},
            edges=[{"from_node": "b", "from_output": "value", "to_node": "a", "to_input": "value"}],
        )

        self.assertIn("WF009", _codes(validate_graph(graph, self.registry)))

    def test_validation_reports_common_graph_errors(self) -> None:
        graph = _graph(
            [
                {"node_id": "a", "node_type": "test.echo", "inputs": {"value": "$nodes.missing.outputs.value"}},
                {"node_id": "a", "node_type": "test.unknown", "inputs": {}},
                {"node_id": "c", "node_type": "test.echo", "params": {"mode": "bad"}, "inputs": {}},
            ],
            inputs={},
        )

        codes = _codes(validate_graph(graph, self.registry))

        self.assertIn("WF002", codes)
        self.assertIn("WF003", codes)
        self.assertIn("WF007", codes)
        self.assertIn("WF008", codes)
        self.assertIn("WF010", codes)

    def test_cycle_detection(self) -> None:
        graph = _graph(
            [
                {"node_id": "a", "node_type": "test.echo", "inputs": {"value": "$nodes.b.outputs.value"}},
                {"node_id": "b", "node_type": "test.echo", "inputs": {"value": "$nodes.a.outputs.value"}},
            ],
            inputs={},
        )

        self.assertIn("WF006", _codes(validate_graph(graph, self.registry)))

    def test_guarded_node_requires_confirm_when_enabled(self) -> None:
        graph = _graph(
            [{"node_id": "danger", "node_type": "test.guarded", "inputs": {"value": "x"}, "side_effects": [RENAMES_FILES]}],
            inputs={},
        )

        self.assertIn("WF014", _codes(validate_graph(graph, self.registry)))

    def test_run_workflow_writes_artifacts_and_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "runs"
            graph = _graph(
                [
                    {"node_id": "a", "node_type": "test.echo", "inputs": {"value": "$workflow.inputs.seed"}},
                    {"node_id": "b", "node_type": "test.echo", "inputs": {"value": "$nodes.a.outputs.value"}},
                ],
                inputs={"seed": "ok"},
            )

            result = run_workflow(graph, registry=self.registry, run_root=run_root)
            run_log = json.loads((run_root / result["run_id"] / "run_log.json").read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "completed")
            self.assertEqual(run_log["topology"], ["a", "b"])
            self.assertTrue((run_root / result["run_id"] / "artifacts" / "b.value.json").exists())

    def test_disabled_node_records_skipped_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = _graph(
                [
                    {
                        "node_id": "effect",
                        "node_type": "test.effect",
                        "enabled": False,
                        "inputs": {"value": "x"},
                        "side_effects": [WRITES_CSV],
                    }
                ],
                inputs={},
            )

            result = run_workflow(graph, registry=self.registry, run_root=Path(tmp))
            node = result["nodes"]["effect"]

            self.assertEqual(node["status"], "skipped_disabled")
            self.assertEqual(node["side_effects"][0]["decision"], "skipped_disabled")

    def test_missing_side_effect_decision_fails_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            graph = _graph(
                [{"node_id": "effect", "node_type": "test.missing_decision", "inputs": {"value": "x"}, "side_effects": [WRITES_CSV]}],
                inputs={},
            )

            result = run_workflow(graph, registry=self.registry, run_root=Path(tmp))

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["nodes"]["effect"]["status"], "failed")

    def test_replay_blocks_side_effect_and_hydrates_previous_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            graph = _graph(
                [{"node_id": "effect", "node_type": "test.effect", "inputs": {"value": "x"}, "side_effects": [WRITES_CSV]}],
                inputs={},
            )
            first = run_workflow(graph, registry=self.registry, run_root=run_root)

            replayed = replay_workflow(run_root / first["run_id"], registry=self.registry, run_root=run_root)

            self.assertEqual(replayed["status"], "completed_with_blocked")
            self.assertEqual(replayed["nodes"]["effect"]["side_effects"][0]["decision"], "blocked_replay")
            self.assertIn("value", replayed["nodes"]["effect"]["outputs"])


def _graph(nodes: list[dict], *, inputs: dict, edges: list[dict] | None = None):
    return normalize_graph(
        {
            "schema_version": 1,
            "workflow_id": "test",
            "display_name": "Test",
            "description": "Test graph",
            "inputs": inputs,
            "nodes": nodes,
            "edges": edges or [],
        }
    )


def _codes(issues):
    return {issue.code for issue in issues}


if __name__ == "__main__":
    unittest.main()
