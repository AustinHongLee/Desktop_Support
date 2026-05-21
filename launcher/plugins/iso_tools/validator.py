from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from launcher.plugins.iso_tools.issues import ChecklistIssue


@dataclass(frozen=True)
class IsoChecklistContext:
    folder: Path | None
    combine_pdf: Path | None
    page_folder: Path | None
    pdfs: tuple[Path, ...]
    iso_list_path: Path | None
    iso_table_loaded: bool
    iso_record_count: int
    iso_candidate: Path | None
    cv2_available: bool
    rapidocr_available: bool
    serial_region_default: bool
    drawing_region_default: bool
    blocking_rename_count: int
    problem_row_count: int
    checked_rename_count: int


@dataclass(frozen=True)
class ChecklistSummary:
    blocked: int
    warnings: int
    pending: int
    running: int

    @property
    def can_start(self) -> bool:
        return self.blocked == 0 and self.running == 0


def validate_autopilot_checklist(context: IsoChecklistContext) -> tuple[ChecklistIssue, ...]:
    return (
        _folder_issue(context),
        _pdf_issue(context),
        _iso_issue(context),
        _ocr_issue(context),
        _profile_issue(context),
        _output_issue(context),
        _rename_issue(context),
    )


def summarize_checklist(issues: tuple[ChecklistIssue, ...]) -> ChecklistSummary:
    return ChecklistSummary(
        blocked=sum(1 for issue in issues if issue.state == "blocked"),
        warnings=sum(1 for issue in issues if issue.state == "warn"),
        pending=sum(1 for issue in issues if issue.state == "pending"),
        running=sum(1 for issue in issues if issue.state == "running"),
    )


def _folder_issue(context: IsoChecklistContext) -> ChecklistIssue:
    folder = context.folder
    if folder is not None and folder.exists():
        return ChecklistIssue("folder", "PF01", "ready", "目前資料夾", str(folder))
    return ChecklistIssue("folder", "E001", "blocked", "目前資料夾", "請先選擇含 PDF / ISO List 的資料夾", True)


def _pdf_issue(context: IsoChecklistContext) -> ChecklistIssue:
    if context.combine_pdf is not None and context.pdfs == (context.combine_pdf,):
        return ChecklistIssue("pdf", "PF02", "warn", "PDF 來源", f"找到合併 PDF，啟動後會拆頁：{context.combine_pdf.name}")
    if context.pdfs:
        return ChecklistIssue("pdf", "PF02", "ready", "PDF 來源", f"已載入 {len(context.pdfs)} 個頁面 PDF")
    if context.combine_pdf is not None:
        return ChecklistIssue("pdf", "PF02", "warn", "PDF 來源", f"已選合併 PDF：{context.combine_pdf.name}")
    return ChecklistIssue("pdf", "E002", "blocked", "PDF 來源", "找不到可處理的 PDF", True)


def _iso_issue(context: IsoChecklistContext) -> ChecklistIssue:
    if context.iso_record_count:
        return ChecklistIssue("iso", "PF03", "ready", "ISO List / 欄位", f"已套用 {context.iso_record_count} 筆 ISO 對照資料")
    if context.iso_table_loaded:
        return ChecklistIssue("iso", "PF04", "warn", "ISO List / 欄位", "已讀取 Sheet，欄位尚未套用")
    if context.iso_list_path is not None:
        return ChecklistIssue("iso", "PF03", "warn", "ISO List / 欄位", f"已選 ISO List，尚未讀取：{context.iso_list_path.name}")
    if context.iso_candidate is not None:
        return ChecklistIssue("iso", "PF03", "warn", "ISO List / 欄位", f"找到候選 ISO List，啟動後會自動載入：{context.iso_candidate.name}")
    return ChecklistIssue("iso", "E003", "blocked", "ISO List / 欄位", "找不到 .xlsx / .csv ISO List", True)


def _ocr_issue(context: IsoChecklistContext) -> ChecklistIssue:
    if context.cv2_available and context.rapidocr_available:
        return ChecklistIssue("ocr", "PF07", "ready", "OCR / 影像判讀", "OpenCV + RapidOCR 可用")
    if context.cv2_available:
        return ChecklistIssue("ocr", "W001", "warn", "OCR / 影像判讀", "OpenCV 可用；RapidOCR 未安裝，判讀穩定度會下降")
    return ChecklistIssue("ocr", "E004", "blocked", "OCR / 影像判讀", "OpenCV 未安裝，無法執行影像判讀", True)


def _profile_issue(context: IsoChecklistContext) -> ChecklistIssue:
    if not context.serial_region_default or not context.drawing_region_default:
        return ChecklistIssue("profile", "PF05", "ready", "圖框 Profile", "已載入圖框 / ROI profile")
    return ChecklistIssue("profile", "W002", "warn", "圖框 Profile", "使用預設判讀區，首次專案建議先調校")


def _output_issue(context: IsoChecklistContext) -> ChecklistIssue:
    folder = context.folder
    if folder is None:
        return ChecklistIssue("output", "PF06", "pending", "輸出位置", "等待資料夾")
    if folder.exists() and os.access(folder, os.W_OK):
        return ChecklistIssue("output", "PF06", "ready", "輸出位置", "輸出資料夾可寫入")
    return ChecklistIssue("output", "E005", "blocked", "輸出位置", "輸出資料夾不可寫入", True)


def _rename_issue(context: IsoChecklistContext) -> ChecklistIssue:
    if context.blocking_rename_count:
        return ChecklistIssue("rename", "E006", "blocked", "命名計畫", f"{context.blocking_rename_count} 個命名阻擋項目", True)
    if context.problem_row_count:
        return ChecklistIssue("rename", "W003", "warn", "命名計畫", f"{context.problem_row_count} 列需要人工確認")
    if context.checked_rename_count:
        return ChecklistIssue("rename", "PF08", "ready", "命名計畫", f"{context.checked_rename_count} 個 PDF 可更名")
    if context.pdfs:
        return ChecklistIssue("rename", "PF08", "pending", "命名計畫", "尚未產生命名計畫")
    return ChecklistIssue("rename", "PF08", "pending", "命名計畫", "等待 PDF 來源")
