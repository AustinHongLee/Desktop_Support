from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    workflow_cancel_action,
    workflow_list_runs_action,
    workflow_read_run_log_action,
    workflow_run_action,
    workflow_run_status_action,
)
from launcher.app.tauri_workflow_job import run_job
from launcher.plugins.iso_tools.workflow.nodes.apply import ApplyRenameNode
from launcher.plugins.iso_tools.workflow.nodes.detection import BatchDetectSerialsNode
from launcher.plugins.iso_tools.workflow.nodes.export import ExportDebugBundleNode, ExportPlanCsvNode
from launcher.plugins.iso_tools.workflow.nodes.iso_list import LoadIsoTableNode
from launcher.plugins.iso_tools.workflow.nodes.pilot import PilotReportNode, RoiDistributionNode
from launcher.plugins.iso_tools.workflow.nodes.plan import BuildPlanNode
from launcher.plugins.iso_tools.workflow.nodes.profile import LoadProfileNode, SaveDraftProfileNode
from launcher.plugins.iso_tools.workflow.nodes.sources import DiscoverSourcesNode, SplitPdfNode
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES, WRITES_JOB_FILES
from launcher.plugins.iso_tools.workflow.registry import get_registry


class IsoWorkflowJobTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = get_registry()
        registry.clear_for_tests()
        for node_cls in (
            ApplyRenameNode,
            BatchDetectSerialsNode,
            BuildPlanNode,
            DiscoverSourcesNode,
            ExportDebugBundleNode,
            ExportPlanCsvNode,
            LoadIsoTableNode,
            LoadProfileNode,
            PilotReportNode,
            RoiDistributionNode,
            SaveDraftProfileNode,
            SplitPdfNode,
        ):
            registry.register(node_cls)

    def test_workflow_run_sync_job_writes_status_and_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso_list = root / "iso_list.xlsx"
            _write_iso_list(iso_list)
            env = _env(root)

            with patch.dict("os.environ", env), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=lambda job_dir: run_job(job_dir),
            ):
                job = workflow_run_action(
                    IsoWorkflowRequest(
                        action="workflow_run",
                        workflow=_load_table_graph(),
                        workflow_inputs={"iso_list": str(iso_list)},
                    )
                )
                status = workflow_run_status_action(
                    IsoWorkflowRequest(action="workflow_run_status", workflow_job_id=job["workflow_job_id"])
                )
                runs = workflow_list_runs_action(IsoWorkflowRequest(action="workflow_list_runs"))
                run_log = workflow_read_run_log_action(
                    IsoWorkflowRequest(action="workflow_read_run_log", workflow_run_id=job["workflow_run_id"])
                )

        self.assertEqual(job["state"], "completed")
        self.assertEqual(status["result"]["status"], "completed")
        self.assertEqual(status["nodes"]["load_table"]["status"], "success")
        self.assertEqual(runs["run_count"], 1)
        self.assertEqual(run_log["nodes"]["load_table"]["status"], "success")

    def test_workflow_cancel_before_first_node_marks_nodes_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso_list = root / "iso_list.xlsx"
            _write_iso_list(iso_list)

            def spawn_cancelled(job_dir: Path) -> None:
                _write_json(job_dir / "cancel.json", {"cancelled_at": "test"})
                run_job(job_dir)

            with patch.dict("os.environ", _env(root)), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=spawn_cancelled,
            ):
                job = workflow_run_action(
                    IsoWorkflowRequest(
                        action="workflow_run",
                        workflow=_two_node_graph(),
                        workflow_inputs={"iso_list": str(iso_list)},
                    )
                )

        self.assertEqual(job["state"], "cancelled")
        self.assertEqual(job["result"]["status"], "cancelled")
        self.assertEqual(job["result"]["nodes"]["load_a"]["status"], "not_run")
        self.assertEqual(job["result"]["nodes"]["load_b"]["status"], "not_run")

    def test_workflow_cancel_action_sets_cancel_requested_for_running_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_root = root / "jobs"
            job_dir = job_root / "job-1"
            job_dir.mkdir(parents=True)
            _write_json(job_dir / "job.json", {"workflow_job_id": "job-1", "job_id": "job-1", "state": "running"})

            with patch.dict("os.environ", _env(root)):
                job = workflow_cancel_action(IsoWorkflowRequest(action="workflow_cancel", workflow_job_id="job-1"))
                cancel_exists = (job_dir / "cancel.json").exists()

        self.assertEqual(job["state"], "cancel_requested")
        self.assertTrue(cancel_exists)

    def test_replay_mode_rejects_allow_before_creating_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict("os.environ", _env(root)):
                with self.assertRaisesRegex(ValueError, "replay"):
                    workflow_run_action(
                        IsoWorkflowRequest(
                            action="workflow_run",
                            workflow_mode="replay",
                            workflow_run_id="missing",
                            workflow_allow=(RENAMES_FILES,),
                        )
                    )

        self.assertFalse((Path(tmp) / "jobs").exists())

    def test_workflow_allow_rejects_auto_side_effect_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict("os.environ", _env(root)):
                with self.assertRaisesRegex(ValueError, "workflow_allow"):
                    workflow_run_action(
                        IsoWorkflowRequest(
                            action="workflow_run",
                            workflow=_load_table_graph(),
                            workflow_allow=(WRITES_JOB_FILES,),
                        )
                    )

        self.assertFalse((Path(tmp) / "jobs").exists())

    def test_guarded_apply_without_allow_blocks_and_keeps_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "page_001.pdf"
            target = root / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")

            with patch.dict("os.environ", _env(root)), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=lambda job_dir: run_job(job_dir),
            ):
                job = workflow_run_action(
                    IsoWorkflowRequest(
                        action="workflow_run",
                        workflow=_apply_graph(),
                        workflow_inputs={"rows": [_row(source, target)]},
                    )
                )
                source_exists = source.exists()
                target_exists = target.exists()

        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["result"]["status"], "completed_with_blocked")
        self.assertEqual(job["result"]["nodes"]["apply"]["status"], "blocked")
        self.assertEqual(job["result"]["side_effect_summary"]["blocked"][0]["kind"], RENAMES_FILES)
        self.assertTrue(source_exists)
        self.assertFalse(target_exists)

    def test_guarded_apply_with_allow_and_confirm_renames_tmp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "page_001.pdf"
            target = root / "101--PIPE-A.pdf"
            source.write_bytes(b"%PDF-1.4\n")

            with patch.dict("os.environ", _env(root)), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=lambda job_dir: run_job(job_dir),
            ):
                job = workflow_run_action(
                    IsoWorkflowRequest(
                        action="workflow_run",
                        workflow=_apply_graph(),
                        workflow_inputs={"rows": [_row(source, target)]},
                        workflow_allow=(RENAMES_FILES,),
                        workflow_confirm=("apply",),
                    )
                )
                source_exists = source.exists()
                target_exists = target.exists()

        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["result"]["status"], "completed")
        self.assertEqual(job["result"]["nodes"]["apply"]["status"], "success")
        self.assertEqual(job["result"]["side_effect_summary"]["executed"][0]["kind"], RENAMES_FILES)
        self.assertFalse(source_exists)
        self.assertTrue(target_exists)


def _env(root: Path) -> dict[str, str]:
    return {
        "DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT": str(root / "jobs"),
        "DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT": str(root / "runs"),
    }


def _load_table_graph() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "job_load_table",
        "display_name": "Job load table",
        "description": "Read-only job graph.",
        "inputs": {"iso_list": None},
        "nodes": [
            {
                "node_id": "load_table",
                "node_type": "iso.load_iso_table",
                "inputs": {"iso_list": "$workflow.inputs.iso_list"},
            }
        ],
    }


def _two_node_graph() -> dict[str, object]:
    graph = _load_table_graph()
    graph["nodes"] = [
        {"node_id": "load_a", "node_type": "iso.load_iso_table", "inputs": {"iso_list": "$workflow.inputs.iso_list"}},
        {"node_id": "load_b", "node_type": "iso.load_iso_table", "inputs": {"iso_list": "$workflow.inputs.iso_list"}},
    ]
    return graph


def _apply_graph() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "job_apply",
        "display_name": "Job apply",
        "description": "Guarded apply job graph.",
        "inputs": {"rows": []},
        "nodes": [
            {
                "node_id": "apply",
                "node_type": "iso.apply_rename",
                "inputs": {"rows": "$workflow.inputs.rows"},
                "params": {"dry_run": False, "only_ready": True},
                "requires_confirm": True,
            }
        ],
    }


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


def _write_iso_list(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    sheet.append(["1", "PIPE-A"])
    sheet.append(["2", "PIPE-B"])
    workbook.save(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
