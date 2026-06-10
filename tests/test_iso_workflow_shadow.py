from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from pypdf import PdfWriter

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    start_batch_detect,
    workflow_set_shadow_flag_action,
    workflow_shadow_run_action,
)
from launcher.app.tauri_iso_worker import run_job as run_iso_job
from launcher.app.tauri_workflow_job import run_job as run_workflow_job
from launcher.core.paths import PROJECT_ROOT_ENV
from launcher.plugins.iso_tools.workflow.nodes.apply import ApplyRenameNode
from launcher.plugins.iso_tools.workflow.nodes.detection import BatchDetectSerialsNode
from launcher.plugins.iso_tools.workflow.nodes.export import ExportDebugBundleNode, ExportPlanCsvNode
from launcher.plugins.iso_tools.workflow.nodes.iso_list import LoadIsoTableNode
from launcher.plugins.iso_tools.workflow.nodes.pilot import PilotReportNode, RoiDistributionNode
from launcher.plugins.iso_tools.workflow.nodes.plan import BuildPlanNode
from launcher.plugins.iso_tools.workflow.nodes.profile import LoadProfileNode, SaveDraftProfileNode
from launcher.plugins.iso_tools.workflow.nodes.sources import DiscoverSourcesNode, SplitPdfNode
from launcher.plugins.iso_tools.workflow.registry import get_registry


class IsoWorkflowShadowTests(unittest.TestCase):
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

    def test_shadow_run_records_v2_parity_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "sample"
            work.mkdir()
            pdf = work / "combine.pdf"
            iso_list = work / "iso_list.xlsx"
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)

            with patch.dict(os.environ, _env(root)), patch(
                "launcher.app.tauri_iso_workflow._spawn_iso_worker",
                side_effect=lambda job_dir: run_iso_job(Path(job_dir)),
            ), patch(
                "launcher.app.tauri_iso_workflow._spawn_workflow_job",
                side_effect=lambda job_dir: run_workflow_job(Path(job_dir)),
            ):
                iso_job = start_batch_detect(
                    IsoWorkflowRequest(
                        action="start_batch_detect",
                        work_folder=work,
                        combine_pdf=pdf,
                        iso_list=iso_list,
                        detect_serials=False,
                    )
                )
                before_files = _relative_files(work)
                iso_job_path = root / "jobs" / "iso" / iso_job["job_id"] / "job.json"
                iso_job_bytes = iso_job_path.read_bytes()

                workflow_set_shadow_flag_action(IsoWorkflowRequest(action="workflow_set_shadow_flag", workflow={"enabled": True}))
                first = workflow_shadow_run_action(IsoWorkflowRequest(action="workflow_shadow_run", job_id=iso_job["job_id"]))
                second = workflow_shadow_run_action(IsoWorkflowRequest(action="workflow_shadow_run", job_id=iso_job["job_id"]))

                parity_summary = first["parity_summary"]
                report = json.loads(Path(parity_summary["report_path"]).read_text(encoding="utf-8"))
                workflow_job_dirs = [path for path in (root / "jobs" / "workflow").iterdir() if path.is_dir()]

            self.assertEqual(first["state"], "completed")
            self.assertEqual(first["workflow_job_id"], second["workflow_job_id"])
            self.assertEqual(len(workflow_job_dirs), 1)
            self.assertEqual(parity_summary["status"], "recorded")
            self.assertTrue(parity_summary["equal"])
            self.assertEqual(parity_summary["violation_count"], 0)
            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["trigger"], "shadow")
            self.assertEqual(report["sample_kind"], "real")
            self.assertEqual(report["iso_job_id"], iso_job["job_id"])
            self.assertEqual(report["workflow_run_id"], first["workflow_run_id"])
            self.assertIn("legacy_ms", report["timing"])
            self.assertIn("workflow_ms", report["timing"])
            self.assertEqual(_relative_files(work), before_files)
            self.assertEqual(iso_job_path.read_bytes(), iso_job_bytes)

    def test_shadow_run_requires_flag_and_completed_iso_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            iso_job_dir = root / "jobs" / "iso" / "job-1"
            iso_job_dir.mkdir(parents=True)
            _write_json(iso_job_dir / "job.json", {"job_id": "job-1", "state": "running"})
            _write_json(iso_job_dir / "request.json", {"action": "start_batch_detect"})

            with patch.dict(os.environ, _env(root)):
                with self.assertRaisesRegex(ValueError, "影子驗證未啟用"):
                    workflow_shadow_run_action(IsoWorkflowRequest(action="workflow_shadow_run", job_id="job-1"))
                workflow_set_shadow_flag_action(IsoWorkflowRequest(action="workflow_set_shadow_flag", workflow={"enabled": True}))
                with self.assertRaisesRegex(ValueError, "尚未完成"):
                    workflow_shadow_run_action(IsoWorkflowRequest(action="workflow_shadow_run", job_id="job-1"))

    def test_shadow_run_rejects_escaped_job_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, _env(root)):
                workflow_set_shadow_flag_action(IsoWorkflowRequest(action="workflow_set_shadow_flag", workflow={"enabled": True}))
                with self.assertRaises(FileNotFoundError):
                    workflow_shadow_run_action(IsoWorkflowRequest(action="workflow_shadow_run", job_id="../escape"))


def _env(root: Path) -> dict[str, str]:
    return {
        PROJECT_ROOT_ENV: str(root / "project"),
        "DESKTOP_SUPPORT_JOB_ROOT": str(root / "jobs" / "iso"),
        "DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT": str(root / "jobs" / "workflow"),
        "DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT": str(root / "runs" / "workflow"),
        "DESKTOP_SUPPORT_ISO_RUN_ROOT": str(root / "runs" / "iso"),
    }


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_iso_list(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "DWG NO.ALL"
    sheet.append(["流水號", "圖號"])
    sheet.append([1, "PIPE-A"])
    sheet.append([2, "PIPE-B"])
    workbook.save(path)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _relative_files(folder: Path) -> list[str]:
    return sorted(str(path.relative_to(folder)).replace("\\", "/") for path in folder.rglob("*") if path.is_file())


if __name__ == "__main__":
    unittest.main()
