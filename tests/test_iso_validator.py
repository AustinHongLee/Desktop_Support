from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.plugins.iso_tools.issues import issue_state_text
from launcher.plugins.iso_tools.validator import IsoChecklistContext, summarize_checklist, validate_autopilot_checklist


class IsoValidatorTests(unittest.TestCase):
    def test_missing_sources_are_blocked(self) -> None:
        issues = validate_autopilot_checklist(_context())
        by_key = {issue.key: issue for issue in issues}
        summary = summarize_checklist(issues)

        self.assertEqual(by_key["folder"].state, "blocked")
        self.assertEqual(by_key["pdf"].state, "blocked")
        self.assertEqual(by_key["iso"].state, "blocked")
        self.assertFalse(summary.can_start)
        self.assertGreaterEqual(summary.blocked, 3)

    def test_ready_sources_allow_run_with_default_profile_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine_p001.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            iso = folder / "iso.xlsx"
            iso.write_bytes(b"placeholder")

            issues = validate_autopilot_checklist(
                _context(
                    folder=folder,
                    pdfs=(pdf,),
                    iso_list_path=iso,
                    iso_record_count=1,
                    cv2_available=True,
                    rapidocr_available=True,
                    checked_rename_count=1,
                )
            )

        by_key = {issue.key: issue for issue in issues}
        summary = summarize_checklist(issues)
        self.assertEqual(by_key["folder"].state, "ready")
        self.assertEqual(by_key["pdf"].state, "ready")
        self.assertEqual(by_key["iso"].state, "ready")
        self.assertEqual(by_key["ocr"].state, "ready")
        self.assertEqual(by_key["profile"].state, "warn")
        self.assertEqual(by_key["rename"].state, "ready")
        self.assertTrue(summary.can_start)
        self.assertEqual(summary.warnings, 1)

    def test_rename_blockers_stop_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "page.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")

            issues = validate_autopilot_checklist(
                _context(
                    folder=folder,
                    pdfs=(pdf,),
                    iso_record_count=1,
                    cv2_available=True,
                    rapidocr_available=True,
                    blocking_rename_count=2,
                )
            )

        by_key = {issue.key: issue for issue in issues}
        self.assertEqual(by_key["rename"].state, "blocked")
        self.assertEqual(by_key["rename"].code, "E006")
        self.assertFalse(summarize_checklist(issues).can_start)

    def test_ocr_missing_cv2_is_blocking(self) -> None:
        issues = validate_autopilot_checklist(_context(cv2_available=False, rapidocr_available=False))
        by_key = {issue.key: issue for issue in issues}

        self.assertEqual(by_key["ocr"].state, "blocked")
        self.assertEqual(by_key["ocr"].code, "E004")

    def test_issue_state_text_is_chinese(self) -> None:
        self.assertEqual(issue_state_text("ready"), "OK")
        self.assertEqual(issue_state_text("warn"), "注意")
        self.assertEqual(issue_state_text("blocked"), "阻擋")


def _context(
    *,
    folder: Path | None = None,
    combine_pdf: Path | None = None,
    page_folder: Path | None = None,
    pdfs: tuple[Path, ...] = (),
    iso_list_path: Path | None = None,
    iso_table_loaded: bool = False,
    iso_record_count: int = 0,
    iso_candidate: Path | None = None,
    cv2_available: bool = False,
    rapidocr_available: bool = False,
    serial_region_default: bool = True,
    drawing_region_default: bool = True,
    blocking_rename_count: int = 0,
    problem_row_count: int = 0,
    checked_rename_count: int = 0,
) -> IsoChecklistContext:
    return IsoChecklistContext(
        folder=folder,
        combine_pdf=combine_pdf,
        page_folder=page_folder,
        pdfs=pdfs,
        iso_list_path=iso_list_path,
        iso_table_loaded=iso_table_loaded,
        iso_record_count=iso_record_count,
        iso_candidate=iso_candidate,
        cv2_available=cv2_available,
        rapidocr_available=rapidocr_available,
        serial_region_default=serial_region_default,
        drawing_region_default=drawing_region_default,
        blocking_rename_count=blocking_rename_count,
        problem_row_count=problem_row_count,
        checked_rename_count=checked_rename_count,
    )


if __name__ == "__main__":
    unittest.main()
