from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from launcher.plugins.iso_tools.serial_vision import SerialVisionResult
from launcher.plugins.iso_tools.workflow.cli import main as workflow_cli_main
from launcher.plugins.iso_tools.workflow.parity import SAFE_WORKFLOW_PATH, compare_plans, run_parity
from tests.test_tauri_iso_workflow import _FakeDetector, _write_pdf


class IsoWorkflowParityTests(unittest.TestCase):
    def test_golden_fixture_matches_without_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = _fixture_inputs(root, detect_serials=False)

            report = run_parity(inputs, workflow_path=SAFE_WORKFLOW_PATH, work_dir=root / "parity")

        self.assertTrue(report.equal, report.to_payload()["violations"])
        self.assertEqual(report.violations, [])
        self.assertTrue(report.legacy_digest.startswith("sha256:"))
        self.assertEqual(report.legacy_digest, report.workflow_digest)

    def test_detection_fixture_matches_with_deterministic_detector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = _fixture_inputs(root, detect_serials=True)
            detector = lambda: _FakeDetector(
                [
                    SerialVisionResult("1", 0.91, "stub"),
                    SerialVisionResult("2", 0.92, "stub"),
                    SerialVisionResult("3", 0.93, "stub"),
                ]
            )

            with patch("launcher.app.tauri_iso_worker._SerialDetector", detector), patch("launcher.app.tauri_iso_workflow._SerialDetector", detector):
                report = run_parity(inputs, workflow_path=SAFE_WORKFLOW_PATH, work_dir=root / "parity")

        self.assertTrue(report.equal, report.to_payload()["violations"])

    def test_mutation_sentinel_reports_row_violation(self) -> None:
        legacy = _minimal_plan()
        workflow = deepcopy(legacy)
        workflow["rows"][1]["serial"] = "999"

        report = compare_plans(legacy, workflow)

        self.assertFalse(report.equal)
        self.assertTrue(
            any(item.get("field") == "rows.serial" and item.get("row_page") == 2 for item in report.violations),
            report.violations,
        )

    def test_cli_parity_writes_report_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = _fixture_inputs(root, detect_serials=False)
            inputs_path = root / "inputs.json"
            report_path = root / "report.json"
            inputs_path.write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = workflow_cli_main(
                    [
                        "parity",
                        "--inputs-json",
                        str(inputs_path),
                        "--workflow",
                        str(SAFE_WORKFLOW_PATH),
                        "--work-dir",
                        str(root / "parity"),
                        "--report-out",
                        str(report_path),
                        "--json",
                    ]
                )
            payload = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["equal"])
        self.assertEqual(payload["violations"], [])

    def test_real_sample_matches_when_available(self) -> None:
        inputs = _real_sample_inputs()
        if inputs is None:
            self.skipTest("C:/Users/a0976/Downloads/t does not contain an obvious PDF + ISO list sample")
        with tempfile.TemporaryDirectory() as tmp:
            report = run_parity(inputs, workflow_path=SAFE_WORKFLOW_PATH, work_dir=Path(tmp) / "parity")
        self.assertTrue(report.equal, report.to_payload()["violations"])


def _fixture_inputs(root: Path, *, detect_serials: bool) -> dict[str, object]:
    sample = root / "sample"
    sample.mkdir()
    pdf = sample / "combine.pdf"
    iso_list = sample / "iso_list.xlsx"
    _write_pdf(pdf, pages=3)
    _write_iso_rows(iso_list, [("1", "PIPE-A"), ("2", "PIPE-B"), ("3", "PIPE-C")])
    return {
        "work_folder": str(sample),
        "combine_pdf": str(pdf),
        "iso_list": str(iso_list),
        "sheet_name": "ISO",
        "serial_col": 0,
        "line_col": 1,
        "pattern": "{serial}--{line}.pdf",
        "detect_serials": detect_serials,
        "confidence_threshold": 0.7,
        "serial_region": None,
        "drawing_region": None,
    }


def _write_iso_rows(path: Path, rows: list[tuple[str, str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    for serial, line in rows:
        sheet.append([serial, line])
    workbook.save(path)


def _minimal_plan() -> dict[str, object]:
    rows = [
        _row(1, "1", "PIPE-A", "ready", True),
        _row(2, "2", "PIPE-B", "ready", True),
    ]
    return {
        "schema_version": 1,
        "action": "batch_detect_result",
        "created_at": "ignored",
        "source": {
            "kind": "combine_pdf",
            "work_folder": "C:/fixture/sample",
            "combine_pdf": "C:/fixture/sample/combine.pdf",
            "page_folder": "C:/fixture/sample/combine_pages",
            "iso_list": "C:/fixture/sample/iso_list.xlsx",
            "sheet_name": "ISO",
            "serial_col": 0,
            "line_col": 1,
            "record_count": 2,
            "pattern": "{serial}--{line}.pdf",
            "detect_serials": False,
            "confidence_threshold": 0.7,
        },
        "summary": {"total": 2, "ready": 2, "warn": 0, "blocked": 0, "selected": 2},
        "rows": rows,
        "issues": [{"code": "PDF02", "detail": "ignored"}],
        "pilot_results": [
            {"id": "P01", "status": "ready", "blocks_apply": False},
            {"id": "P15", "status": "warn", "blocks_apply": False},
        ],
    }


def _row(page: int, serial: str, line_no: str, status: str, selected: bool) -> dict[str, object]:
    return {
        "id": f"row-{page}",
        "page": page,
        "source_path": f"C:/fixture/sample/combine_pages/combine_p{page:03d}.pdf",
        "source_name": f"combine_p{page:03d}.pdf",
        "serial": serial,
        "line_no": line_no,
        "new_name": f"{serial}--{line_no}.pdf",
        "target_path": f"C:/fixture/sample/combine_pages/{serial}--{line_no}.pdf",
        "status": status,
        "selected": selected,
        "confidence": 1.0,
        "vision_message": "",
        "note": "",
    }


def _real_sample_inputs() -> dict[str, object] | None:
    folder = Path("C:/Users/a0976/Downloads/t")
    if not folder.exists():
        return None
    pdfs = sorted(folder.glob("*.pdf"))
    iso_lists = sorted([*folder.glob("*.xlsx"), *folder.glob("*.xlsm")])
    if not pdfs or not iso_lists:
        return None
    return {
        "work_folder": str(folder),
        "combine_pdf": str(pdfs[0]),
        "iso_list": str(iso_lists[0]),
        "sheet_name": "",
        "serial_col": None,
        "line_col": None,
        "pattern": "{serial}--{line}.pdf",
        "detect_serials": False,
        "confidence_threshold": 0.7,
        "serial_region": None,
        "drawing_region": None,
    }
