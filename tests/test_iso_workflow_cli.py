from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from launcher.plugins.iso_tools.workflow import cli
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import get_registry
from launcher.plugins.iso_tools.workflow.schema import NodeSpec, PortSpec


class CliEchoNode(WorkflowNode):
    spec = NodeSpec(
        node_type="test.cli_echo",
        display_name="CLI Echo",
        description="Echo for CLI smoke tests.",
        inputs=(PortSpec("value", "json"),),
        outputs=(PortSpec("value", "json"),),
    )

    def run(self, ctx):
        return {"value": ctx.inputs["value"]}


class IsoWorkflowCliTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = get_registry()
        registry.clear_for_tests()
        registry.register(CliEchoNode)

    def test_list_nodes_json(self) -> None:
        code, payload = _call(["list-nodes", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["nodes"][0]["node_type"], "test.cli_echo")

    def test_validate_reports_valid_graph_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = _write_workflow(Path(tmp))

            code, payload = _call(["validate", "--workflow", str(workflow), "--json"])

        self.assertEqual(code, 0)
        self.assertTrue(payload["valid"])

    def test_validate_returns_exit_2_for_unknown_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow = Path(tmp) / "bad.workflow.json"
            workflow.write_text(json.dumps({**_workflow_payload(), "nodes": [{"node_id": "x", "node_type": "missing"}]}), encoding="utf-8")

            code, payload = _call(["validate", "--workflow", str(workflow), "--json"])

        self.assertEqual(code, 2)
        self.assertFalse(payload["valid"])

    def test_run_writes_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            workflow = _write_workflow(Path(tmp))

            code, payload = _call(["run", "--workflow", str(workflow), "--run-root", str(root), "--json"])

            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["run_dir"], str(root / payload["run_id"]))
            self.assertTrue((root / payload["run_id"] / "run_log.json").exists())
            run_log = _read_run_log(Path(payload["run_dir"]))
            self.assertEqual(run_log["inputs"]["seed"], "ok")

    def test_list_runs_reports_existing_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            workflow = _write_workflow(Path(tmp))
            _call(["run", "--workflow", str(workflow), "--run-root", str(root), "--json"])

            code, payload = _call(["list-runs", "--run-root", str(root), "--json"])

            self.assertEqual(code, 0)
            self.assertEqual(len(payload["runs"]), 1)
            self.assertEqual(payload["runs"][0]["workflow_id"], "cli_test")

    def test_replay_uses_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            workflow = _write_workflow(Path(tmp))
            _code, first = _call(["run", "--workflow", str(workflow), "--run-root", str(root), "--set", "seed=override", "--json"])

            code, replayed = _call(["replay", "--run", first["run_id"], "--run-root", str(root), "--json"])

            self.assertEqual(code, 0)
            self.assertEqual(replayed["status"], "completed")
            self.assertEqual(_read_output(Path(replayed["run_dir"]), "echo", "value"), "override")

    def test_run_node_hydrates_upstream_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            workflow = _write_workflow(Path(tmp), chained=True)
            _code, first = _call(["run", "--workflow", str(workflow), "--run-root", str(root), "--json"])

            code, payload = _call(["run-node", "--run", first["run_id"], "--node", "target", "--run-root", str(root), "--json"])

            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(_read_output(Path(payload["run_dir"]), "target", "value"), "ok")


def _call(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    payload = json.loads(stream.getvalue())
    return code, payload


def _write_workflow(folder: Path, *, chained: bool = False) -> Path:
    path = folder / "test.workflow.json"
    path.write_text(json.dumps(_workflow_payload(chained=chained), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _workflow_payload(*, chained: bool = False) -> dict:
    nodes = [
        {
            "node_id": "echo",
            "node_type": "test.cli_echo",
            "inputs": {"value": "$workflow.inputs.seed"},
        }
    ]
    if chained:
        nodes.append(
            {
                "node_id": "target",
                "node_type": "test.cli_echo",
                "inputs": {"value": "$nodes.echo.outputs.value"},
            }
        )
    return {
        "schema_version": 1,
        "workflow_id": "cli_test",
        "display_name": "CLI Test",
        "description": "CLI test graph",
        "inputs": {"seed": "ok"},
        "nodes": nodes,
    }


def _read_run_log(run_dir: Path) -> dict:
    return json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))


def _read_output(run_dir: Path, node_id: str, port: str) -> object:
    run_log = _read_run_log(run_dir)
    artifact_ref = run_log["nodes"][node_id]["outputs"][port]["artifact_ref"]
    return json.loads((run_dir / artifact_ref).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
