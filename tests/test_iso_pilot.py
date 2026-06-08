from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, build_iso_plan, pilot_report
from launcher.plugins.iso_tools.pilot import PILOT_ITEM_IDS, build_pilot_report
from tests.test_tauri_iso_workflow import _write_iso_list, _write_pdf


class IsoPilotTests(unittest.TestCase):
    def test_pilot_report_contains_minimum_12_items_and_apply_blockers(self) -> None:
        plan = {
            "source": {
                "kind": "page_folder",
                "work_folder": "C:/work",
                "page_folder": "C:/work/pages",
                "pdf_count": 2,
                "iso_list": "C:/work/iso.xlsx",
                "sheet_name": "ISO",
                "headers": ["流水號", "圖號"],
                "serial_col": 0,
                "line_col": 1,
                "record_count": 1,
                "pattern": "{serial}--{line}.pdf",
                "detect_serials": True,
            },
            "summary": {"total": 2, "ready": 1, "warn": 0, "blocked": 1, "selected": 1},
            "rows": [
                {
                    "page": 1,
                    "serial": "1",
                    "line_no": "PIPE-A",
                    "new_name": "1--PIPE-A.pdf",
                    "status": "ready",
                    "selected": True,
                    "confidence": 0.91,
                    "vision_message": "OK",
                },
                {
                    "page": 2,
                    "serial": "",
                    "line_no": "",
                    "new_name": "",
                    "status": "blocked",
                    "selected": False,
                    "confidence": 0.0,
                    "note": "無法產生新檔名",
                },
            ],
            "issues": [],
        }

        report = build_pilot_report(request={"work_folder": "C:/work", "detect_serials": True}, plan=plan)
        by_id = {item["id"]: item for item in report["items"]}

        self.assertEqual(tuple(by_id), PILOT_ITEM_IDS)
        self.assertEqual(by_id["P01"]["status"], "ready")
        self.assertEqual(by_id["P09"]["status"], "blocked")
        self.assertTrue(by_id["P09"]["blocks_apply"])
        self.assertEqual(by_id["P12"]["status"], "blocked")
        self.assertEqual(report["summary"]["blocked"], 3)

    def test_build_iso_plan_includes_pilot_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)

            plan = build_iso_plan(IsoWorkflowRequest(action="plan", combine_pdf=pdf, iso_list=iso_list))

        self.assertEqual(len(plan["pilot_results"]), len(PILOT_ITEM_IDS))
        self.assertEqual(plan["pilot_results"][0]["id"], "P01")
        self.assertEqual(plan["pilot_summary"]["blocked"], 0)

    def test_pilot_report_action_can_build_from_current_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            iso_list = folder / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            report = pilot_report(IsoWorkflowRequest(action="pilot_report", combine_pdf=pdf, iso_list=iso_list))

        self.assertEqual(report["action"], "pilot_report")
        self.assertEqual(len(report["items"]), len(PILOT_ITEM_IDS))
        self.assertTrue(report["source"]["pdf_count"])


if __name__ == "__main__":
    unittest.main()
