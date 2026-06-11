from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, workflow_run_action, workflow_run_from_action
from launcher.app.tauri_workflow_job import run_job
from launcher.plugins.iso_tools.workflow.executor import run_from_node, run_workflow
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.registry import get_registry
from launcher.plugins.iso_tools.workflow.schema import NodeSpec, PortSpec, normalize_graph


class RerunEchoNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.rerun_echo",
        display_name="Rerun echo",
        description="Echoes a value with an optional suffix.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        params_schema={"suffix": {"type": "text", "default": ""}},
    )

    def run(self, ctx):
        return {"value": f"{ctx.inputs['value']}{ctx.params.get('suffix', '')}"}


class RerunGuardedNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.rerun_guarded",
        display_name="Rerun guarded",
        description="Guarded node for rerun safety tests.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
        side_effects=(RENAMES_FILES,),
        guarded=True,
        requires_confirm_default=True,
    )

    def run(self, ctx):
        decision = ctx.request_side_effect(RENAMES_FILES, {"node": ctx.node_id})
        if decision != "executed":
            ctx.mark_blocked(decision)
        return {"value": decision}


class IsoWorkflowRerunTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = get_registry()
        registry.clear_for_tests()
        registry.register(RerunEchoNode)
        registry.register(RerunGuardedNode)

    def test_run_from_node_hydrates_upstream_and_reruns_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = _chain_graph()
            first = run_workflow(graph, inputs={"seed": "A"}, run_root=root)

            rerun = run_from_node(root / first["run_id"], "b", inputs={"seed": "Z"}, run_root=root)

            self.assertEqual(rerun["status"], "completed")
            self.assertEqual(rerun["source_run_id"], first["run_id"])
            self.assertEqual(rerun["topology"], ["b", "c"])
            self.assertNotIn("a", rerun["nodes"])
            self.assertEqual(_read_output(Path(rerun["run_dir"]), "b", "value"), "Ab")
            self.assertEqual(_read_output(Path(rerun["run_dir"]), "c", "value"), "Abc")

    def test_run_from_node_keeps_guarded_policy_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = _guarded_graph()
            first = run_workflow(
                graph,
                inputs={"seed": "A"},
                run_root=root,
                policy=SideEffectPolicy(allowed_guarded=frozenset({RENAMES_FILES}), confirmed_nodes=frozenset({"danger"})),
            )

            rerun = run_from_node(root / first["run_id"], "danger", run_root=root)

            self.assertEqual(rerun["status"], "completed_with_blocked")
            self.assertEqual(rerun["nodes"]["danger"]["status"], "blocked")
            self.assertEqual(rerun["nodes"]["danger"]["side_effects"][0]["decision"], "blocked_policy")

    def test_tauri_run_from_action_uses_job_and_source_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT": str(root / "jobs"),
                "DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT": str(root / "runs"),
            }
            with patch.dict("os.environ", env), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=lambda job_dir: run_job(job_dir),
            ):
                first = workflow_run_action(
                    IsoWorkflowRequest(
                        action="workflow_run",
                        workflow=_chain_graph().to_payload(),
                        workflow_inputs={"seed": "A"},
                    )
                )
                rerun = workflow_run_from_action(
                    IsoWorkflowRequest(
                        action="workflow_run_from",
                        workflow_run_id=first["workflow_run_id"],
                        workflow_node_id="b",
                        workflow_inputs={"seed": "Z"},
                    )
                )

        self.assertEqual(rerun["state"], "completed")
        self.assertEqual(rerun["result"]["status"], "completed")
        self.assertEqual(rerun["result"]["source_run_id"], first["workflow_run_id"])
        self.assertEqual(rerun["result"]["topology"], ["b", "c"])


def _chain_graph():
    return normalize_graph(
        {
            "schema_version": 1,
            "workflow_id": "rerun_chain",
            "display_name": "Rerun chain",
            "description": "Rerun test graph",
            "inputs": {"seed": "A"},
            "nodes": [
                {"node_id": "a", "node_type": "test.rerun_echo", "inputs": {"value": "$workflow.inputs.seed"}},
                {"node_id": "b", "node_type": "test.rerun_echo", "inputs": {"value": "$nodes.a.outputs.value"}, "params": {"suffix": "b"}},
                {"node_id": "c", "node_type": "test.rerun_echo", "inputs": {"value": "$nodes.b.outputs.value"}, "params": {"suffix": "c"}},
            ],
        }
    )


def _guarded_graph():
    return normalize_graph(
        {
            "schema_version": 1,
            "workflow_id": "rerun_guarded",
            "display_name": "Rerun guarded",
            "description": "Rerun guarded graph",
            "inputs": {"seed": "A"},
            "nodes": [
                {"node_id": "a", "node_type": "test.rerun_echo", "inputs": {"value": "$workflow.inputs.seed"}},
                {
                    "node_id": "danger",
                    "node_type": "test.rerun_guarded",
                    "inputs": {"value": "$nodes.a.outputs.value"},
                    "requires_confirm": True,
                    "side_effects": [RENAMES_FILES],
                },
            ],
        }
    )


def _read_output(run_dir: Path, node_id: str, port: str) -> str:
    return json.loads((run_dir / "artifacts" / f"{node_id}.{port}.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
