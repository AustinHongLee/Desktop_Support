from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_workflow, validate_graph
from launcher.plugins.iso_tools.workflow.nodes.apply import ApplyRenameNode
from launcher.plugins.iso_tools.workflow.nodes.profile import SaveDraftProfileNode
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES, WRITES_PROFILE, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.registry import NodeRegistry
from launcher.plugins.iso_tools.workflow.schema import normalize_graph


class IsoWorkflowApplySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry()
        self.registry.register(ApplyRenameNode)
        self.registry.register(SaveDraftProfileNode)

    def test_default_apply_dry_run_simulates_without_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "inputs": {"rows": "$workflow.inputs.rows"},
                        "requires_confirm": True,
                    }
                ],
                inputs={"rows": [_row(source, target)]},
            )

            result = run_workflow(graph, registry=self.registry, run_root=folder / "runs")
            preview = _read_output(Path(result["run_dir"]), "apply", "result")
            source_exists = source.exists()
            target_exists = target.exists()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["nodes"]["apply"]["side_effects"][0]["decision"], "simulated")
        self.assertEqual(preview["action"], "apply_preview")
        self.assertTrue(source_exists)
        self.assertFalse(target_exists)

    def test_disabled_apply_cannot_rename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "enabled": False,
                        "inputs": {"rows": "$workflow.inputs.rows"},
                    }
                ],
                inputs={"rows": [_row(source, target)]},
            )

            result = run_workflow(graph, registry=self.registry, run_root=folder / "runs")
            source_exists = source.exists()
            target_exists = target.exists()

        self.assertEqual(result["nodes"]["apply"]["status"], "skipped_disabled")
        self.assertEqual(result["nodes"]["apply"]["side_effects"][0]["decision"], "skipped_disabled")
        self.assertTrue(source_exists)
        self.assertFalse(target_exists)

    def test_enabled_apply_without_requires_confirm_is_wf014(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "inputs": {"rows": "$workflow.inputs.rows"},
                        "params": {"dry_run": False},
                    }
                ],
                inputs={"rows": [_row(folder / "a.pdf", folder / "b.pdf")]},
            )

            issues = validate_graph(graph, self.registry)

        self.assertIn("WF014", {issue.code for issue in issues})

    def test_enabled_apply_without_allow_and_confirm_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "inputs": {"rows": "$workflow.inputs.rows"},
                        "params": {"dry_run": False},
                        "requires_confirm": True,
                    }
                ],
                inputs={"rows": [_row(source, target)]},
            )

            result = run_workflow(graph, registry=self.registry, run_root=folder / "runs")
            source_exists = source.exists()
            target_exists = target.exists()

        self.assertEqual(result["status"], "completed_with_blocked")
        self.assertEqual(result["nodes"]["apply"]["status"], "blocked")
        self.assertEqual(result["nodes"]["apply"]["side_effects"][0]["decision"], "blocked_policy")
        self.assertTrue(source_exists)
        self.assertFalse(target_exists)

    def test_enabled_apply_with_allow_confirm_and_dry_run_false_renames_tmp_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "inputs": {"rows": "$workflow.inputs.rows"},
                        "params": {"dry_run": False},
                        "requires_confirm": True,
                    }
                ],
                inputs={"rows": [_row(source, target)]},
            )
            policy = SideEffectPolicy(
                mode="run",
                allowed_guarded=frozenset({RENAMES_FILES}),
                confirmed_nodes=frozenset({"apply"}),
            )

            result = run_workflow(graph, registry=self.registry, run_root=folder / "runs", policy=policy)
            renamed_count = _read_output(Path(result["run_dir"]), "apply", "renamed_count")
            source_exists = source.exists()
            target_exists = target.exists()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["nodes"]["apply"]["side_effects"][0]["decision"], "executed")
        self.assertEqual(renamed_count, 1)
        self.assertFalse(source_exists)
        self.assertTrue(target_exists)

    def test_replay_hard_blocks_renames_even_with_allow_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            graph = _graph(
                [
                    {
                        "node_id": "apply",
                        "node_type": "iso.apply_rename",
                        "inputs": {"rows": "$workflow.inputs.rows"},
                        "params": {"dry_run": False},
                        "requires_confirm": True,
                    }
                ],
                inputs={"rows": [_row(source, target)]},
            )
            policy = SideEffectPolicy(
                mode="run",
                allowed_guarded=frozenset({RENAMES_FILES}),
                confirmed_nodes=frozenset({"apply"}),
            )
            first = run_workflow(graph, registry=self.registry, run_root=folder / "runs", policy=policy)

            replayed = replay_workflow(
                Path(first["run_dir"]),
                registry=self.registry,
                run_root=folder / "runs",
                policy=SideEffectPolicy(
                    mode="replay",
                    allowed_guarded=frozenset({RENAMES_FILES}),
                    confirmed_nodes=frozenset({"apply"}),
                    include_auto_in_replay=True,
                ),
            )
            source_exists = source.exists()
            target_exists = target.exists()

        self.assertEqual(replayed["status"], "completed_with_blocked")
        self.assertEqual(replayed["nodes"]["apply"]["side_effects"][0]["decision"], "blocked_replay")
        self.assertFalse(source_exists)
        self.assertTrue(target_exists)

    def test_save_draft_profile_blocks_without_guarded_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "job"
            folder.mkdir()
            state_path = Path(tmp) / "state.json"
            graph = _save_profile_graph(folder, pattern="{serial}-{line}.pdf")

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                result = run_workflow(graph, registry=self.registry, run_root=Path(tmp) / "runs")
                draft = AppStateStore(state_path).iso_naming_profile_draft(folder)

        self.assertEqual(result["status"], "completed_with_blocked")
        self.assertEqual(result["nodes"]["save_profile"]["side_effects"][0]["decision"], "blocked_policy")
        self.assertIsNone(draft)

    def test_save_draft_profile_executes_with_allow_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "job"
            folder.mkdir()
            state_path = Path(tmp) / "state.json"
            graph = _save_profile_graph(folder, pattern="{serial}-{line}.pdf")
            policy = SideEffectPolicy(
                mode="run",
                allowed_guarded=frozenset({WRITES_PROFILE}),
                confirmed_nodes=frozenset({"save_profile"}),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                result = run_workflow(graph, registry=self.registry, run_root=Path(tmp) / "runs", policy=policy)
                draft = AppStateStore(state_path).iso_naming_profile_draft(folder)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["nodes"]["save_profile"]["side_effects"][0]["decision"], "executed")
        self.assertEqual(draft["pattern"], "{serial}-{line}.pdf")

    def test_replay_hard_blocks_profile_writes_even_with_allow_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "job"
            folder.mkdir()
            state_path = Path(tmp) / "state.json"
            graph = _save_profile_graph(folder, pattern="{serial}-{line}.pdf")
            policy = SideEffectPolicy(
                mode="run",
                allowed_guarded=frozenset({WRITES_PROFILE}),
                confirmed_nodes=frozenset({"save_profile"}),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                first = run_workflow(graph, registry=self.registry, run_root=Path(tmp) / "runs", policy=policy)
                store = AppStateStore(state_path)
                store.set_iso_naming_profile_draft(folder, {"pattern": "sentinel.pdf"})
                replayed = replay_workflow(
                    Path(first["run_dir"]),
                    registry=self.registry,
                    run_root=Path(tmp) / "runs",
                    policy=SideEffectPolicy(
                        mode="replay",
                        allowed_guarded=frozenset({WRITES_PROFILE}),
                        confirmed_nodes=frozenset({"save_profile"}),
                        include_auto_in_replay=True,
                    ),
                )
                draft = AppStateStore(state_path).iso_naming_profile_draft(folder)

        self.assertEqual(replayed["status"], "completed_with_blocked")
        self.assertEqual(replayed["nodes"]["save_profile"]["side_effects"][0]["decision"], "blocked_replay")
        self.assertEqual(draft["pattern"], "sentinel.pdf")


def _graph(nodes: list[dict], *, inputs: dict):
    return normalize_graph(
        {
            "schema_version": 1,
            "workflow_id": "iso_apply_safety_test",
            "display_name": "ISO Apply Safety Test",
            "description": "Phase 6 guarded node tests",
            "inputs": inputs,
            "nodes": nodes,
        }
    )


def _save_profile_graph(folder: Path, *, pattern: str):
    return _graph(
        [
            {
                "node_id": "save_profile",
                "node_type": "iso.save_draft_profile",
                "inputs": {
                    "profile": "$workflow.inputs.profile",
                    "work_folder": "$workflow.inputs.work_folder",
                },
                "requires_confirm": True,
            }
        ],
        inputs={
            "work_folder": str(folder),
            "profile": {
                "pattern": pattern,
                "confidence_threshold": 0.75,
                "serial_region": {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.4},
                "drawing_region": {"left": 0.5, "top": 0.6, "width": 0.3, "height": 0.2},
            },
        },
    )


def _row(source: Path, target: Path) -> dict[str, object]:
    return {
        "id": "row-1",
        "source_path": str(source),
        "source_name": source.name,
        "target_path": str(target),
        "new_name": target.name,
        "status": "ready",
        "selected": True,
    }


def _read_output(run_dir: Path, node_id: str, port: str) -> object:
    run_log = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    artifact_ref = run_log["nodes"][node_id]["outputs"][port]["artifact_ref"]
    return json.loads((run_dir / artifact_ref).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
