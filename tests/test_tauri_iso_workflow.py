from __future__ import annotations

import csv
import tempfile
import unittest
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from pypdf import PdfWriter

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    build_iso_plan,
    build_rename_plan,
    discover_sources,
    export_plan_csv,
    load_iso_profile,
    load_iso_table,
    publish_iso_profile_action,
    replay_run_log_action,
    revert_iso_profile_action,
    save_iso_draft_profile,
    save_iso_profile,
    split_iso_pdf,
    workflow_list_nodes_action,
    workflow_load_action,
    workflow_plan_from_run_action,
    workflow_read_artifact_action,
    workflow_validate_action,
)
from launcher.app.tauri_iso_worker import run_job
from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.profile import IsoNamingProfile, save_iso_naming_profile
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult


class TauriIsoWorkflowTests(unittest.TestCase):
    def test_build_iso_plan_splits_combine_pdf_and_maps_iso_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)

            plan = build_iso_plan(IsoWorkflowRequest(action="plan", combine_pdf=pdf, iso_list=iso_list))

        self.assertEqual(plan["summary"]["total"], 2)
        self.assertEqual(plan["summary"]["ready"], 2)
        self.assertEqual(plan["rows"][0]["new_name"], "1--PIPE-A.pdf")
        self.assertEqual(plan["rows"][1]["new_name"], "2--PIPE-B.pdf")

    def test_subprocess_reads_utf8_json_paths_on_windows_codepage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "HP6精濾區配管工程-ISO"
            folder.mkdir()
            pdf = folder / "合併圖.pdf"
            iso_list = folder / "圖資清單-115.04.23.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            request = {
                "action": "plan",
                "combine_pdf": str(pdf),
                "iso_list": str(iso_list),
            }
            result = subprocess.run(
                [sys.executable, "-m", "launcher.app.tauri_iso_workflow"],
                input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
            )

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(payload["summary"]["ready"], 1)
        self.assertEqual(payload["source"]["iso_list"], str(iso_list))

    def test_replay_run_log_rebuilds_plan_without_creating_new_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            pdf = root / "combine.pdf"
            iso_list = root / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            request = {
                "action": "plan",
                "combine_pdf": str(pdf),
                "iso_list": str(iso_list),
                "run_id": "iso-replay-test",
            }
            subprocess.run(
                [sys.executable, "-m", "launcher.app.tauri_iso_workflow"],
                input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "DESKTOP_SUPPORT_ISO_RUN_ROOT": str(run_root)},
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_ISO_RUN_ROOT": str(run_root)}):
                replay = replay_run_log_action(IsoWorkflowRequest(action="replay_run_log", run_id="iso-replay-test"))
                run_dirs = [path for path in run_root.iterdir() if path.is_dir()]

        self.assertEqual(replay["action"], "replay_run_log")
        self.assertTrue(replay["replay_dry_run"])
        self.assertEqual(replay["source_run_id"], "iso-replay-test")
        self.assertEqual(replay["rows"][0]["new_name"], "1--PIPE-A.pdf")
        self.assertEqual(len(run_dirs), 1)

    def test_workflow_readonly_actions_list_load_and_validate_safe_poc(self) -> None:
        workflow_path = Path("launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json")

        nodes = workflow_list_nodes_action(IsoWorkflowRequest(action="workflow_list_nodes"))
        loaded = workflow_load_action(IsoWorkflowRequest(action="workflow_load", workflow_path=workflow_path))
        validated = workflow_validate_action(IsoWorkflowRequest(action="workflow_validate", workflow_path=workflow_path))
        bad = workflow_validate_action(
            IsoWorkflowRequest(
                action="workflow_validate",
                workflow={
                    "schema_version": 1,
                    "workflow_id": "bad",
                    "display_name": "Bad",
                    "description": "Bad graph",
                    "inputs": {},
                    "nodes": [{"node_id": "missing", "node_type": "iso.missing", "inputs": {}}],
                },
            )
        )

        self.assertEqual(nodes["node_count"], 12)
        guarded = {item["node_type"]: item for item in nodes["nodes"] if item.get("guarded")}
        self.assertEqual(guarded["iso.apply_rename"]["side_effects"], ["renames_files"])
        self.assertEqual(guarded["iso.save_draft_profile"]["side_effects"], ["writes_profile"])
        self.assertTrue(loaded["valid"])
        self.assertEqual(loaded["graph"]["workflow_id"], "iso_pdf_safe_poc")
        self.assertTrue(validated["valid"])
        self.assertEqual(len(validated["edges"]), 7)
        self.assertEqual(validated["topology"][0], "discover")
        self.assertFalse(bad["valid"])
        self.assertIn("WF003", {issue["code"] for issue in bad["issues"]})

    def test_workflow_projection_actions_read_plan_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "workflow_runs"
            run_dir = run_root / "wf-action"
            rows = [
                {
                    "id": "row-1",
                    "page": 1,
                    "source_path": str(root / "page_001.pdf"),
                    "source_name": "page_001.pdf",
                    "serial": "1",
                    "line_no": "PIPE-A",
                    "new_name": "1--PIPE-A.pdf",
                    "target_path": str(root / "1--PIPE-A.pdf"),
                    "status": "ready",
                    "selected": True,
                    "confidence": 1.0,
                    "vision_message": "",
                    "note": "",
                }
            ]
            _write_projection_run(run_dir, rows)

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT": str(run_root)}):
                plan = workflow_plan_from_run_action(
                    IsoWorkflowRequest(action="workflow_plan_from_run", workflow_run_id="wf-action")
                )
                artifact = workflow_read_artifact_action(
                    IsoWorkflowRequest(
                        action="workflow_read_artifact",
                        workflow_run_id="wf-action",
                        workflow_node_id="batch",
                        workflow_port="rows",
                    )
                )

        self.assertEqual(plan["action"], "workflow_plan_from_run")
        self.assertEqual(plan["summary"]["selected"], 1)
        self.assertEqual(plan["provenance"]["workflow_run_id"], "wf-action")
        self.assertEqual(artifact["payload"][0]["new_name"], "1--PIPE-A.pdf")

    def test_work_folder_autodetects_combine_pdf_and_iso_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "HP6-ISO圖號清單.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            plan = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))

        self.assertEqual(plan["source"]["kind"], "combine_pdf")
        self.assertEqual(plan["source"]["iso_list"], str(iso_list))
        self.assertEqual(plan["summary"]["ready"], 1)

    def test_phase_0b_commands_are_split_and_export_plan_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "HP6-ISO圖號清單.xlsx"
            export_path = folder / "rename_plan.csv"
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)

            discovery = discover_sources(IsoWorkflowRequest(action="discover_sources", work_folder=folder))
            split = split_iso_pdf(IsoWorkflowRequest(action="split_pdf", combine_pdf=pdf))
            table = load_iso_table(IsoWorkflowRequest(action="load_iso_table", work_folder=folder))
            plan = build_rename_plan(IsoWorkflowRequest(action="build_rename_plan", work_folder=folder))
            export = export_plan_csv(
                IsoWorkflowRequest(
                    action="export_plan_csv",
                    export_path=export_path,
                    rows=tuple(plan["rows"]),
                )
            )

            with export_path.open("r", newline="", encoding="utf-8-sig") as handle:
                exported_rows = list(csv.DictReader(handle))

        self.assertEqual(discovery["action"], "discover_sources")
        self.assertEqual(discovery["detected_combine_pdf"], str(pdf))
        self.assertEqual(discovery["detected_iso_list"], str(iso_list))
        self.assertEqual(split["action"], "split_pdf")
        self.assertEqual(split["source"]["pdf_count"], 2)
        self.assertEqual(len(split["pages"]), 2)
        self.assertEqual(table["action"], "load_iso_table")
        self.assertEqual(table["source"]["record_count"], 2)
        self.assertEqual(table["sample_records"][0]["line_no"], "PIPE-A")
        self.assertEqual(plan["action"], "build_rename_plan")
        self.assertEqual(plan["summary"]["ready"], 2)
        self.assertEqual(export["action"], "export_plan_csv")
        self.assertEqual(export["export_path"], str(export_path))
        self.assertEqual(export["row_count"], 2)
        self.assertEqual(exported_rows[0]["new_name"], "1--PIPE-A.pdf")
        self.assertTrue(exported_rows[0]["created_at"])

    def test_phase_0c_worker_writes_progress_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            job_dir = folder / "jobs" / "job-1"
            job_dir.mkdir(parents=True)
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)
            _write_json(job_dir / "request.json", {"action": "start_batch_detect", "combine_pdf": str(pdf), "iso_list": str(iso_list)})
            _write_json(job_dir / "job.json", _job_payload("job-1"))

            job = run_job(job_dir)

        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["progress"]["total"], 2)
        self.assertEqual(job["progress"]["done"], 2)
        self.assertEqual(job["rows"][0]["new_name"], "1--PIPE-A.pdf")
        self.assertEqual(job["rows"][1]["new_name"], "2--PIPE-B.pdf")
        self.assertEqual(job["result"]["summary"]["ready"], 2)

    def test_phase_0c_worker_honors_cancel_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            job_dir = folder / "jobs" / "job-2"
            job_dir.mkdir(parents=True)
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)
            _write_json(job_dir / "request.json", {"action": "start_batch_detect", "combine_pdf": str(pdf), "iso_list": str(iso_list)})
            _write_json(job_dir / "job.json", _job_payload("job-2"))
            _write_json(job_dir / "cancel.json", {"cancelled_at": "test"})

            job = run_job(job_dir)

        self.assertEqual(job["state"], "cancelled")
        self.assertEqual(job["progress"]["done"], 0)
        self.assertEqual(job["rows"], [])

    def test_load_profile_action_restores_folder_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            iso_list = folder / "iso_list.xlsx"
            profile = IsoNamingProfile(
                pattern="{serial}_{line}.pdf",
                iso_list_path=iso_list,
                sheet_name="ISO",
                serial_col=0,
                line_col=1,
            )
            save_iso_naming_profile(AppStateStore(state_path), folder, profile)

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                payload = load_iso_profile(IsoWorkflowRequest(action="load_profile", work_folder=folder))

        self.assertTrue(payload["exists"])
        self.assertEqual(payload["folder"], str(folder))
        self.assertEqual(payload["pattern"], "{serial}_{line}.pdf")
        self.assertEqual(payload["iso_list_path"], str(iso_list))
        self.assertEqual(payload["serial_col"], 0)
        self.assertEqual(payload["line_col"], 1)

    def test_load_profile_discovers_combine_pdf_from_work_folder_without_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                payload = load_iso_profile(IsoWorkflowRequest(action="load_profile", work_folder=folder))

        self.assertFalse(payload["exists"])
        self.assertEqual(payload["detected_combine_pdf"], str(pdf))
        self.assertEqual(payload["detected_page_folder"], str(folder / "combine_pages"))
        self.assertFalse(payload["detected_page_folder_exists"])
        self.assertEqual(payload["detected_iso_list"], str(iso_list))

    def test_save_profile_action_writes_folder_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            iso_list = folder / "iso_list.xlsx"

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                payload = save_iso_profile(
                    IsoWorkflowRequest(
                        action="save_profile",
                        work_folder=folder,
                        iso_list=iso_list,
                        sheet_name="ISO",
                        serial_col=2,
                        line_col=5,
                        pattern="{serial}-{line}.pdf",
                    )
                )
                restored = load_iso_profile(IsoWorkflowRequest(action="load_profile", work_folder=folder))

        self.assertTrue(payload["exists"])
        self.assertEqual(restored["iso_list_path"], str(iso_list))
        self.assertEqual(restored["sheet_name"], "ISO")
        self.assertEqual(restored["serial_col"], 2)
        self.assertEqual(restored["line_col"], 5)
        self.assertEqual(restored["pattern"], "{serial}-{line}.pdf")

    def test_save_draft_profile_does_not_change_published_plan_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                folder,
                IsoNamingProfile(
                    pattern="{serial}_{line}.pdf",
                    iso_list_path=iso_list,
                    sheet_name="ISO",
                    serial_col=0,
                    line_col=1,
                ),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                draft = save_iso_draft_profile(
                    IsoWorkflowRequest(
                        action="save_draft_profile",
                        profile_folder=folder,
                        iso_list=iso_list,
                        sheet_name="ISO",
                        serial_col=0,
                        line_col=1,
                        pattern="{serial}-{line}.pdf",
                    )
                )
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))

        self.assertEqual(draft["profile_scope"], "draft")
        self.assertTrue(draft["published_exists"])
        self.assertTrue(draft["draft_exists"])
        self.assertEqual(plan["source"]["pattern"], "{serial}_{line}.pdf")
        self.assertEqual(plan["rows"][0]["new_name"], "1_PIPE-A.pdf")

    def test_publish_and_revert_profile_actions_control_plan_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                folder,
                IsoNamingProfile(
                    pattern="{serial}_{line}.pdf",
                    iso_list_path=iso_list,
                    sheet_name="ISO",
                    serial_col=0,
                    line_col=1,
                ),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                save_iso_draft_profile(
                    IsoWorkflowRequest(
                        action="save_draft_profile",
                        profile_folder=folder,
                        iso_list=iso_list,
                        sheet_name="ISO",
                        serial_col=0,
                        line_col=1,
                        pattern="{serial}-{line}.pdf",
                    )
                )
                published = publish_iso_profile_action(IsoWorkflowRequest(action="publish_profile", profile_folder=folder))
                plan_after_publish = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))
                reverted = revert_iso_profile_action(IsoWorkflowRequest(action="revert_profile", profile_folder=folder))
                plan_after_revert = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))

        self.assertEqual(published["profile_scope"], "published")
        self.assertFalse(published["draft_exists"])
        self.assertGreaterEqual(published["history_count"], 1)
        self.assertEqual(plan_after_publish["source"]["pattern"], "{serial}-{line}.pdf")
        self.assertEqual(plan_after_publish["rows"][0]["new_name"], "1-PIPE-A.pdf")
        self.assertEqual(reverted["pattern"], "{serial}_{line}.pdf")
        self.assertGreaterEqual(reverted["history_count"], 1)
        self.assertEqual(plan_after_revert["rows"][0]["new_name"], "1_PIPE-A.pdf")

    def test_build_iso_plan_uses_profile_defaults_when_request_omits_iso_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                folder,
                IsoNamingProfile(
                    pattern="{serial}_{line}.pdf",
                    iso_list_path=iso_list,
                    sheet_name="ISO",
                    serial_col=0,
                    line_col=1,
                ),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))

        self.assertTrue(plan["source"]["profile"]["exists"])
        self.assertEqual(plan["source"]["iso_list"], str(iso_list))
        self.assertEqual(plan["source"]["pattern"], "{serial}_{line}.pdf")
        self.assertEqual(plan["rows"][0]["new_name"], "1_PIPE-A.pdf")

    def test_build_iso_plan_uses_legacy_pages_folder_profile_from_work_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            pages = folder / "combine_pages"
            pages.mkdir()
            page_pdf = pages / "combine_p001.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_pdf(page_pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                pages,
                IsoNamingProfile(
                    pattern="{serial}_{line}.pdf",
                    iso_list_path=iso_list,
                    sheet_name="ISO",
                    serial_col=0,
                    line_col=1,
                ),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                loaded = load_iso_profile(IsoWorkflowRequest(action="load_profile", work_folder=folder))
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", work_folder=folder))

        self.assertTrue(loaded["exists"])
        self.assertEqual(loaded["folder"], str(pages))
        self.assertEqual(loaded["detected_combine_pdf"], str(pdf))
        self.assertEqual(loaded["detected_page_folder"], str(pages))
        self.assertTrue(loaded["detected_page_folder_exists"])
        self.assertTrue(plan["source"]["profile"]["exists"])
        self.assertEqual(plan["source"]["profile"]["folder"], str(pages))
        self.assertEqual(plan["source"]["iso_list"], str(iso_list))
        self.assertEqual(plan["rows"][0]["new_name"], "1_PIPE-A.pdf")

    def test_load_profile_discovers_nearby_iso_when_saved_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "HP6-ISO圖號清單.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                folder,
                IsoNamingProfile(iso_list_path=folder / "missing-old-list.xlsx"),
            )

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                payload = load_iso_profile(IsoWorkflowRequest(action="load_profile", work_folder=folder))

        self.assertTrue(payload["exists"])
        self.assertEqual(payload["iso_list_path"], str(folder / "missing-old-list.xlsx"))
        self.assertEqual(payload["detected_iso_list"], str(iso_list))

    def test_detected_serial_success_is_ready_selected_without_warning_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            with patch("launcher.app.tauri_iso_workflow._SerialDetector", lambda: _FakeDetector([SerialVisionResult("2", 0.93, "OK")])):
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", combine_pdf=pdf, iso_list=iso_list, detect_serials=True))

        row = plan["rows"][0]
        self.assertEqual(row["serial"], "2")
        self.assertEqual(row["status"], "ready")
        self.assertTrue(row["selected"])
        self.assertEqual(row["note"], "")
        self.assertEqual(row["vision_message"], "OK")
        self.assertEqual(plan["summary"]["warn"], 0)

    def test_low_confidence_detected_serial_falls_back_to_page_order_warn_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            with patch("launcher.app.tauri_iso_workflow._SerialDetector", lambda: _FakeDetector([SerialVisionResult("2", 0.51, "weak")])):
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", combine_pdf=pdf, iso_list=iso_list, detect_serials=True))

        row = plan["rows"][0]
        self.assertEqual(row["serial"], "1")
        self.assertEqual(row["status"], "warn")
        self.assertTrue(row["selected"])
        self.assertIn("判讀信心太低", row["note"])
        self.assertEqual(row["vision_message"], "weak")

    def test_existing_iso_filename_skips_vision_detector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            page_folder = folder / "combine_pages"
            page_folder.mkdir()
            page_pdf = page_folder / "1--PIPE-A.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(page_pdf, pages=1)
            _write_iso_list(iso_list)

            with patch("launcher.app.tauri_iso_workflow._SerialDetector", lambda: _ExplodingDetector()):
                plan = build_iso_plan(IsoWorkflowRequest(action="plan", page_folder=page_folder, iso_list=iso_list, detect_serials=True))

        row = plan["rows"][0]
        self.assertEqual(row["serial"], "1")
        self.assertEqual(row["status"], "idle")
        self.assertFalse(row["selected"])
        self.assertEqual(row["vision_message"], "檔名已符合 ISO List")


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_iso_list(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    sheet.append(["1", "PIPE-A"])
    sheet.append(["2", "PIPE-B"])
    workbook.save(path)


class _FakeDetector:
    def __init__(self, results: list[SerialVisionResult]) -> None:
        self._results = results
        self._index = 0

    def detect(self, _source: Path, _lookup: object) -> SerialVisionResult:
        result = self._results[min(self._index, len(self._results) - 1)]
        self._index += 1
        return result


class _ExplodingDetector:
    def detect(self, _source: Path, _lookup: object) -> SerialVisionResult:
        raise AssertionError("detector should not run for existing ISO filenames")


def _job_payload(job_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "action": "batch_detect_job",
        "job_id": job_id,
        "state": "queued",
        "created_at": "test",
        "updated_at": "test",
        "progress": {"total": 0, "done": 0, "percent": 0},
        "rows": [],
        "issues": [],
        "events": [],
        "result": None,
        "error": "",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_projection_run(run_dir: Path, rows: list[dict[str, object]]) -> None:
    run_dir.mkdir(parents=True)
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir()
    plan = {
        "schema_version": 1,
        "action": "batch_detect_result",
        "source": {"pdf_count": len(rows)},
        "summary": {},
        "rows": rows,
        "issues": [],
    }
    result_ref = _write_projection_artifact(run_dir, "batch", "result", plan)
    rows_ref = _write_projection_artifact(run_dir, "batch", "rows", rows)
    run_log = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "mode": "run",
        "workflow_id": "projection_action",
        "run_dir": str(run_dir),
        "graph_hash": "sha256:test",
        "status": "completed",
        "topology": ["batch"],
        "inputs": {},
        "workflow": {"nodes": [{"node_id": "batch", "node_type": "iso.batch_detect_serials"}]},
        "nodes": {
            "batch": {
                "status": "success",
                "outputs": {"result": result_ref, "rows": rows_ref},
                "side_effects": [],
                "logs": [],
            }
        },
        "side_effect_summary": {"executed": [], "blocked": [], "skipped": [], "simulated": []},
        "issues": [],
    }
    _write_json(run_dir / "run_log.json", run_log)


def _write_projection_artifact(run_dir: Path, node_id: str, port: str, payload: object) -> dict[str, object]:
    import hashlib

    path = run_dir / "artifacts" / f"{node_id}.{port}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    data = path.read_bytes()
    return {
        "artifact_ref": str(path.relative_to(run_dir)).replace("\\", "/"),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


if __name__ == "__main__":
    unittest.main()
