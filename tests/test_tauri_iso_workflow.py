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
    save_iso_profile,
    split_iso_pdf,
)
from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.profile import IsoNamingProfile, save_iso_naming_profile


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


if __name__ == "__main__":
    unittest.main()
