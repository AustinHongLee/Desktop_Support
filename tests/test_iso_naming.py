from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.plugins.iso_tools.iso_naming import (
    IsoRecord,
    build_naming_rows,
    format_iso_name,
    guess_iso_columns,
    list_iso_sheets,
    natural_pdf_key,
    parse_iso_filename,
    read_iso_table,
    read_iso_records,
    records_from_table,
)


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


def _write_csv(text: str) -> Path:
    folder = tempfile.TemporaryDirectory()
    path = Path(folder.name) / "iso.csv"
    path.write_text(text, encoding="utf-8-sig")
    _TEMP_DIRS.append(folder)
    return path


class IsoNamingTests(unittest.TestCase):
    def test_read_csv_records_detects_chinese_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "iso.csv"
            csv_path.write_text("流水號,管線號碼\n1,L-100\n2,L-200\n", encoding="utf-8-sig")

            records = read_iso_records(csv_path)

            self.assertEqual(records, [IsoRecord("1", "L-100"), IsoRecord("2", "L-200")])

    def test_read_excel_records_by_sheet_name_and_guess_columns(self) -> None:
        from openpyxl import Workbook

        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "iso.xlsx"
            workbook = Workbook()
            workbook.active.title = "不要讀這張"
            workbook.active.append(["說明", "這張不是 ISO list"])
            sheet = workbook.create_sheet("ISO List")
            sheet.append(["專案", "測試"])
            sheet.append(["流水號", "管線號碼", "備註"])
            sheet.append([1, "L-100", "A"])
            sheet.append([2, "L-200", "B"])
            workbook.save(xlsx_path)

            self.assertEqual(list_iso_sheets(xlsx_path), ["不要讀這張", "ISO List"])
            table = read_iso_table(xlsx_path, sheet_name="ISO List")
            serial_col, line_col = guess_iso_columns(table.headers)
            records = records_from_table(table, serial_col=serial_col, line_col=line_col)

            self.assertEqual(table.sheet_name, "ISO List")
            self.assertEqual(table.header_row_index, 1)
            self.assertEqual(records, [IsoRecord("1", "L-100"), IsoRecord("2", "L-200")])

    def test_records_from_table_supports_manual_column_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "iso.csv"
            csv_path.write_text("管號,備註,排序\nL-100,A,001\nL-200,B,002\n", encoding="utf-8-sig")

            table = read_iso_table(csv_path)
            records = records_from_table(table, serial_col=2, line_col=0)

            self.assertEqual(records, [IsoRecord("001", "L-100"), IsoRecord("002", "L-200")])

    def test_guess_columns_prefers_full_drawing_basename_over_line_no(self) -> None:
        headers = ("source_pdf_name", "dst_pdf_name", "file_basename", "LINE NO.", "Serial")

        serial_col, line_col = guess_iso_columns(headers)

        self.assertEqual(serial_col, 4)
        self.assertEqual(line_col, 2)

    def test_records_from_table_strips_pdf_suffix_and_existing_prefix(self) -> None:
        table = read_iso_table(_write_csv("Serial,dst_pdf_name\n101,101--2-S11-P-20911-003.PDF\n"))

        records = records_from_table(table, serial_col=0, line_col=1)

        self.assertEqual(records, [IsoRecord("101", "2-S11-P-20911-003")])

    def test_parse_iso_filename_extracts_existing_serial_and_drawing_name(self) -> None:
        self.assertEqual(
            parse_iso_filename("101--1-S11U-AI-00001-001.pdf"),
            IsoRecord("101", "1-S11U-AI-00001-001"),
        )

    def test_build_naming_rows_uses_serial_to_lookup_line_no(self) -> None:
        files = [Path("combine_p002.pdf"), Path("combine_p001.pdf")]
        records = [IsoRecord("1", "A"), IsoRecord("2", "B")]

        rows = build_naming_rows(files, records)

        self.assertEqual([row.source.name for row in rows], ["combine_p001.pdf", "combine_p002.pdf"])
        self.assertEqual([row.new_name for row in rows], ["1--A.pdf", "2--B.pdf"])

    def test_format_iso_name_adds_pdf_suffix_when_missing(self) -> None:
        self.assertEqual(format_iso_name("{serial}--{line}", serial="03", line="P-300"), "03--P-300.pdf")

    def test_natural_pdf_key_sorts_page_numbers(self) -> None:
        names = [Path("x_p10.pdf"), Path("x_p2.pdf"), Path("x_p1.pdf")]

        self.assertEqual([path.name for path in sorted(names, key=natural_pdf_key)], ["x_p1.pdf", "x_p2.pdf", "x_p10.pdf"])


if __name__ == "__main__":
    unittest.main()
