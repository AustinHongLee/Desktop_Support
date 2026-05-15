from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter


def split_pdf_pages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    pdfs = [path for path in _files(payload) if path.suffix.lower() == ".pdf"]
    if not pdfs:
        raise ValueError("請先選取 PDF 檔案")

    events: list[dict[str, Any]] = []
    total_pages = 0
    for pdf in pdfs:
        reader = PdfReader(str(pdf))
        page_count = len(reader.pages)
        output_dir = pdf.with_name(f"{pdf.stem}_pages")
        output_dir.mkdir(exist_ok=True)
        width = max(3, len(str(page_count)))

        for index, page in enumerate(reader.pages, start=1):
            writer = PdfWriter()
            writer.add_page(page)
            output = output_dir / f"{pdf.stem}_p{index:0{width}d}.pdf"
            with output.open("wb") as handle:
                writer.write(handle)
        total_pages += page_count
        events.append(
            {
                "type": "artifact",
                "message": f"{pdf.name} 已分割 {page_count} 頁：{output_dir}",
                "path": str(output_dir),
                "count": page_count,
            }
        )

    events.insert(0, {"type": "message", "message": f"共處理 {len(pdfs)} 份 PDF，輸出 {total_pages} 頁。"})
    return events


def _files(payload: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in payload["context"].get("files", [])]

