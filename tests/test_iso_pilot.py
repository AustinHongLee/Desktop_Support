from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, build_iso_plan, pilot_report, roi_distribution
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
        self.assertEqual(by_id["P13"]["status"], "ready")
        self.assertEqual(by_id["P14"]["status"], "blocked")
        self.assertTrue(by_id["P14"]["blocks_apply"])
        self.assertEqual(by_id["P15"]["status"], "ready")
        self.assertEqual(report["summary"]["blocked"], 4)
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(all("freshness" in item and "needs_review" in item and "next_action" in item for item in report["items"]))

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

    def test_pilot_report_marks_stale_when_request_differs_from_plan_source(self) -> None:
        plan = {
            "source": {
                "kind": "page_folder",
                "work_folder": "",
                "page_folder": "",
                "pdf_count": 1,
                "iso_list": "",
                "sheet_name": "ISO",
                "serial_col": 0,
                "line_col": 1,
                "record_count": 1,
                "pattern": "{serial}--{line}.pdf",
                "detect_serials": True,
                "confidence_threshold": 0.70,
                "serial_region": {"left": 0.62, "top": 0, "width": 0.38, "height": 0.24},
            },
            "summary": {"total": 1, "ready": 1, "warn": 0, "blocked": 0, "selected": 1},
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
            ],
            "issues": [],
        }

        report = build_pilot_report(
            request={
                "sheet_name": "ISO-NEW",
                "serial_col": 0,
                "line_col": 1,
                "pattern": "{serial}--{line}.pdf",
                "confidence_threshold": 0.80,
                "serial_region": {"left": 0.5, "top": 0, "width": 0.4, "height": 0.24},
                "detect_serials": True,
            },
            plan=plan,
        )
        by_id = {item["id"]: item for item in report["items"]}

        self.assertEqual(by_id["P15"]["status"], "warn")
        self.assertEqual(by_id["P15"]["freshness"], "stale")
        self.assertFalse(by_id["P15"]["blocks_apply"])
        self.assertIn("sheet_name", by_id["P15"]["metrics"]["changed"])
        self.assertIn("confidence_threshold", by_id["P15"]["metrics"]["changed"])
        self.assertIn("serial_region", by_id["P15"]["metrics"]["changed"])

    def test_profile_missing_paths_block_apply_in_p14(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.xlsx"
            plan = {
                "source": {
                    "work_folder": tmp,
                    "page_folder": "",
                    "pdf_count": 0,
                    "iso_list": str(missing),
                    "sheet_name": "",
                    "record_count": 0,
                    "pattern": "{serial}--{line}.pdf",
                    "detect_serials": False,
                },
                "summary": {"total": 0, "ready": 0, "warn": 0, "blocked": 0, "selected": 0},
                "rows": [],
                "issues": [],
            }

            report = build_pilot_report(request={}, plan=plan)

        by_id = {item["id"]: item for item in report["items"]}
        self.assertEqual(by_id["P14"]["status"], "blocked")
        self.assertTrue(by_id["P14"]["blocks_apply"])
        self.assertGreaterEqual(report["summary"]["blocked"], 1)

    def test_roi_distribution_action_summarizes_confidence_buckets(self) -> None:
        payload = roi_distribution(
            IsoWorkflowRequest(
                action="roi_distribution",
                confidence_threshold=0.80,
                rows=(
                    {"page": 1, "source_name": "p1.pdf", "confidence": 0.91},
                    {"page": 2, "source_name": "p2.pdf", "confidence": 0.50},
                    {"page": 3, "source_name": "p3.pdf", "confidence": 0.0},
                ),
            )
        )

        self.assertEqual(payload["action"], "roi_distribution")
        self.assertEqual(payload["ready"], 1)
        self.assertEqual(payload["low"], 1)
        self.assertEqual(payload["missing"], 1)


if __name__ == "__main__":
    unittest.main()
