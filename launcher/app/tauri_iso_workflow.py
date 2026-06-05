from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.iso_naming import (
    IsoRecord,
    build_record_lookup,
    format_iso_name,
    guess_iso_columns,
    list_iso_sheets,
    natural_pdf_key,
    read_iso_table,
    records_from_table,
    split_pdf_to_pages,
)
from launcher.plugins.iso_tools.profile import IsoNamingProfile, load_iso_naming_profile, save_iso_naming_profile
from launcher.plugins.iso_tools.serial_correction import correct_result_with_iso_lookup
from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion, SerialVisionResult
from launcher.plugins.rename_tools.rename_actions import RenameOperation, _apply_operations, _validate_file_name, _validate_operations

SERIAL_AUTO_FILL_CONFIDENCE = 0.70
DEFAULT_PATTERN = "{serial}--{line}.pdf"
STATE_PATH_ENV = "DESKTOP_SUPPORT_STATE_PATH"


@dataclass(frozen=True)
class IsoWorkflowRequest:
    action: str
    profile_folder: Path | None = None
    work_folder: Path | None = None
    combine_pdf: Path | None = None
    page_folder: Path | None = None
    iso_list: Path | None = None
    sheet_name: str | None = None
    serial_col: int | None = None
    line_col: int | None = None
    pattern: str | None = None
    serial_region: dict[str, Any] | None = None
    drawing_region: dict[str, Any] | None = None
    confidence_threshold: float | None = None
    detect_serials: bool = False
    export_path: Path | None = None
    rows: tuple[dict[str, Any], ...] = ()


def main() -> int:
    _configure_stdio()
    try:
        request = IsoWorkflowRequest(**_normalize_request(json.loads(_read_stdin_json() or "{}")))
        if request.action == "discover_sources":
            payload = discover_sources(request)
        elif request.action == "split_pdf":
            payload = split_iso_pdf(request)
        elif request.action == "load_iso_table":
            payload = load_iso_table(request)
        elif request.action == "plan":
            payload = build_iso_plan(request)
        elif request.action == "build_rename_plan":
            payload = build_rename_plan(request)
        elif request.action == "export_plan_csv":
            payload = export_plan_csv(request)
        elif request.action == "apply":
            payload = apply_iso_plan(request)
        elif request.action == "load_profile":
            payload = load_iso_profile(request)
        elif request.action == "save_profile":
            payload = save_iso_profile(request)
        else:
            raise ValueError(f"unknown action: {request.action}")
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


def build_iso_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    pdfs, source_kind, page_folder, pdf_events = _resolve_pdfs(request)
    request, loaded_profile = _with_profile_defaults(request, resolved_page_folder=page_folder)
    pattern = _plan_pattern(request)
    records, iso_meta = _resolve_iso_records(request)
    lookup = build_record_lookup(records)
    rows, row_events = _build_plan_rows(
        pdfs,
        lookup,
        pattern=pattern,
        detect_serials=request.detect_serials,
    )
    issues = [*pdf_events, *iso_meta["issues"], *row_events]
    summary = _summary(rows)
    return {
        "schema_version": 1,
        "action": "plan",
        "created_at": _now(),
        "source": {
            "kind": source_kind,
            "work_folder": str(request.work_folder or ""),
            "combine_pdf": str(request.combine_pdf or ""),
            "page_folder": str(page_folder or ""),
            "pdf_count": len(pdfs),
            "iso_list": str(iso_meta["iso_list"]),
            "iso_candidates": iso_meta["iso_candidates"],
            "sheet_name": iso_meta["sheet_name"],
            "sheet_options": iso_meta["sheet_options"],
            "headers": iso_meta["headers"],
            "serial_col": iso_meta["serial_col"],
            "line_col": iso_meta["line_col"],
            "record_count": len(records),
            "pattern": pattern,
            "detect_serials": request.detect_serials,
            "profile": loaded_profile,
        },
        "summary": summary,
        "steps": _steps(source_kind, len(pdfs), len(records), request.detect_serials, summary),
        "rows": rows,
        "issues": issues,
    }


def discover_sources(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder, profile, candidates = _load_profile_for_request(request)
    return _profile_response(
        action="discover_sources",
        folder=folder,
        profile=profile or IsoNamingProfile(),
        exists=profile is not None,
        candidates=candidates,
        message=f"已探索來源：{folder}" if folder is not None else "尚未選擇可探索的來源。",
    )


def split_iso_pdf(request: IsoWorkflowRequest) -> dict[str, Any]:
    pdfs, source_kind, page_folder, events = _resolve_pdfs(request)
    return {
        "schema_version": 1,
        "action": "split_pdf",
        "created_at": _now(),
        "source": {
            "kind": source_kind,
            "work_folder": str(request.work_folder or ""),
            "combine_pdf": str(request.combine_pdf or ""),
            "page_folder": str(page_folder or ""),
            "pdf_count": len(pdfs),
        },
        "pages": [
            {
                "page": index,
                "source_path": str(path),
                "source_name": path.name,
            }
            for index, path in enumerate(pdfs, start=1)
        ],
        "issues": events,
    }


def load_iso_table(request: IsoWorkflowRequest) -> dict[str, Any]:
    request, loaded_profile = _with_profile_defaults(request)
    records, iso_meta = _resolve_iso_records(request)
    return {
        "schema_version": 1,
        "action": "load_iso_table",
        "created_at": _now(),
        "source": {
            "work_folder": str(request.work_folder or ""),
            "iso_list": str(iso_meta["iso_list"]),
            "iso_candidates": iso_meta["iso_candidates"],
            "sheet_name": iso_meta["sheet_name"],
            "sheet_options": iso_meta["sheet_options"],
            "headers": iso_meta["headers"],
            "serial_col": iso_meta["serial_col"],
            "line_col": iso_meta["line_col"],
            "record_count": len(records),
            "profile": loaded_profile,
        },
        "sample_records": [
            {"serial": record.serial, "line_no": record.line_no}
            for record in records[:8]
        ],
        "issues": iso_meta["issues"],
    }


def build_rename_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    payload = build_iso_plan(request)
    payload["action"] = "build_rename_plan"
    return payload


def load_iso_profile(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder, profile, candidates = _load_profile_for_request(request)
    if folder is None:
        return _profile_response(
            action="load_profile",
            folder=None,
            profile=IsoNamingProfile(),
            exists=False,
            candidates=candidates,
            message="尚未選擇可對應 profile 的工作資料夾。",
        )
    return _profile_response(
        action="load_profile",
        folder=folder,
        profile=profile or IsoNamingProfile(),
        exists=profile is not None,
        candidates=candidates,
        message=f"已載入資料夾設定：{folder}" if profile is not None else f"此資料夾尚未建立 ISO profile：{folder}",
    )


def save_iso_profile(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder = _profile_folder(request)
    if folder is None:
        raise ValueError("請先選擇工作資料夾，才能儲存 ISO profile。")
    store = _state_store()
    existing = load_iso_naming_profile(store, folder)
    profile = _profile_from_request(request, existing or IsoNamingProfile())
    save_iso_naming_profile(store, folder, profile)
    return _profile_response(
        action="save_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=_profile_folder_candidates(request),
        message=f"已儲存 ISO profile：{folder}",
    )


def apply_iso_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    operations = [
        RenameOperation(Path(row["source_path"]), Path(row["target_path"]))
        for row in request.rows
        if row.get("selected")
    ]
    if not operations:
        return {
            "schema_version": 1,
            "action": "apply",
            "created_at": _now(),
            "renamed_count": 0,
            "rows": [],
            "message": "沒有勾選需要更名的 PDF。",
        }
    _validate_operations(operations)
    _apply_operations(operations)
    return {
        "schema_version": 1,
        "action": "apply",
        "created_at": _now(),
        "renamed_count": len(operations),
        "rows": [
            {
                "source_path": str(operation.source),
                "target_path": str(operation.target),
                "source_name": operation.source.name,
                "target_name": operation.target.name,
            }
            for operation in operations
        ],
        "message": f"已更名 {len(operations)} 個 PDF。",
    }


def export_plan_csv(request: IsoWorkflowRequest) -> dict[str, Any]:
    rows = list(request.rows)
    if not rows:
        rows = build_iso_plan(request)["rows"]
    if not rows:
        raise ValueError("沒有可匯出的命名草稿。")

    export_path = request.export_path or _default_export_path(request, rows)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "selected",
        "page",
        "source_name",
        "serial",
        "line_no",
        "new_name",
        "status",
        "confidence",
        "note",
        "vision_message",
        "source_path",
        "target_path",
    ]
    with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})

    selected_count = sum(1 for row in rows if row.get("selected"))
    return {
        "schema_version": 1,
        "action": "export_plan_csv",
        "created_at": _now(),
        "export_path": str(export_path),
        "row_count": len(rows),
        "selected_count": selected_count,
        "message": f"已匯出命名草稿 CSV：{export_path}",
    }


def _resolve_pdfs(request: IsoWorkflowRequest) -> tuple[list[Path], str, Path | None, list[dict[str, str]]]:
    events: list[dict[str, str]] = []
    if request.page_folder is not None:
        if not request.page_folder.exists() or not request.page_folder.is_dir():
            raise FileNotFoundError(f"頁面資料夾不存在：{request.page_folder}")
        pdfs = _pdfs_from_folder(request.page_folder)
        if not pdfs:
            raise ValueError(f"頁面資料夾沒有 PDF：{request.page_folder}")
        return pdfs, "page_folder", request.page_folder, events

    combine_pdf = request.combine_pdf
    if combine_pdf is None and request.work_folder is not None:
        combine_pdf = _auto_combine_pdf_candidate(request.work_folder)
        if combine_pdf is None:
            pdfs = _pdfs_from_folder(request.work_folder) if request.work_folder.exists() and request.work_folder.is_dir() else []
            if pdfs:
                events.append({"code": "PDF00", "tone": "ready", "title": "使用資料夾內 PDF", "detail": str(request.work_folder)})
                return pdfs, "work_folder_pages", request.work_folder, events

    if combine_pdf is None:
        raise ValueError("請選擇 combine PDF 或頁面 PDF 資料夾。")
    if not combine_pdf.exists():
        raise FileNotFoundError(f"combine PDF 不存在：{combine_pdf}")

    page_folder = combine_pdf.with_name(f"{combine_pdf.stem}_pages")
    if page_folder.exists():
        existing_pages = _pdfs_from_folder(page_folder)
        if existing_pages:
            events.append({"code": "PDF01", "tone": "ready", "title": "使用既有拆頁資料夾", "detail": str(page_folder)})
            return existing_pages, "existing_pages", page_folder, events

    outputs = split_pdf_to_pages(combine_pdf)
    if not outputs:
        raise ValueError("combine PDF 沒有可拆出的頁面。")
    events.append({"code": "PDF02", "tone": "ready", "title": "已拆成單頁 PDF", "detail": f"{len(outputs)} pages"})
    return outputs, "combine_pdf", outputs[0].parent, events


def _resolve_iso_records(request: IsoWorkflowRequest) -> tuple[list[IsoRecord], dict[str, Any]]:
    iso_candidates = [str(path) for path in _nearby_iso_list_candidates(request)]
    iso_list = request.iso_list or (Path(iso_candidates[0]) if iso_candidates else None)
    if iso_list is None:
        raise ValueError("請選擇 ISO List。")
    if not iso_list.exists():
        raise FileNotFoundError(f"ISO List 不存在：{iso_list}")

    sheet_name, sheet_options = _resolve_sheet_name(iso_list, request.sheet_name)
    table = read_iso_table(iso_list, sheet_name=sheet_name)
    guessed_serial_col, guessed_line_col = guess_iso_columns(table.headers)
    serial_col = request.serial_col if request.serial_col is not None else guessed_serial_col
    line_col = request.line_col if request.line_col is not None else guessed_line_col
    if serial_col is None or line_col is None:
        raise ValueError("找不到 ISO List 欄位，請確認有「流水號」與「圖號/檔名」欄位。")
    records = records_from_table(table, serial_col=serial_col, line_col=line_col)
    if not records:
        raise ValueError("ISO List 沒有有效資料。")
    return records, {
        "iso_list": iso_list,
        "iso_candidates": iso_candidates,
        "sheet_name": table.sheet_name,
        "sheet_options": sheet_options,
        "headers": list(table.headers),
        "serial_col": serial_col,
        "line_col": line_col,
        "issues": [
            {
                "code": "ISO01",
                "tone": "ready",
                "title": "ISO List 已載入",
                "detail": f"{table.sheet_name} · {len(records)} rows",
            }
        ],
    }


def _build_plan_rows(
    pdfs: list[Path],
    lookup: dict[str, IsoRecord],
    *,
    pattern: str,
    detect_serials: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    events: list[dict[str, str]] = []
    detector = _SerialDetector() if detect_serials else None
    seen_targets: set[Path] = set()

    for index, source in enumerate(pdfs, start=1):
        default_serial = str(index)
        vision = detector.detect(source, lookup) if detector is not None else SerialVisionResult("", 0.0, "")
        serial, note = _serial_for_row(default_serial, vision, lookup)
        record = lookup.get(serial)
        line_no = record.line_no if record else ""
        new_name = format_iso_name(pattern, serial=serial, line=line_no)
        target = source.with_name(new_name) if new_name else source
        status, status_note = _row_status(source, target, new_name, line_no, note, seen_targets)
        if new_name:
            seen_targets.add(target)
        selected = status == "ready" and new_name != source.name
        row_note = status_note or note
        if row_note:
            events.append({"code": "ROW", "tone": status, "title": source.name, "detail": row_note})
        rows.append(
            {
                "id": f"row-{index}",
                "page": index,
                "source_path": str(source),
                "source_name": source.name,
                "serial": serial,
                "line_no": line_no,
                "new_name": new_name,
                "target_path": str(target),
                "status": status,
                "selected": selected,
                "confidence": round(float(vision.confidence), 3),
                "vision_message": vision.message,
                "note": row_note,
            }
        )
    return rows, events


def _serial_for_row(default_serial: str, vision: SerialVisionResult, lookup: dict[str, IsoRecord]) -> tuple[str, str]:
    if not vision.text:
        return default_serial, vision.message
    result = correct_result_with_iso_lookup(vision, lookup)
    if result.confidence < SERIAL_AUTO_FILL_CONFIDENCE:
        return default_serial, f"判讀信心太低 {result.confidence:.2f}，暫用頁序 {default_serial}"
    if result.text not in lookup:
        return default_serial, f"ISO List 無此流水號 {result.text}，暫用頁序 {default_serial}"
    return result.text, result.message


def _row_status(source: Path, target: Path, new_name: str, line_no: str, note: str, seen_targets: set[Path]) -> tuple[str, str]:
    if not new_name:
        return "blocked", note or "無法產生新檔名"
    try:
        _validate_file_name(Path(new_name).name)
    except ValueError as exc:
        return "blocked", str(exc)
    if not line_no:
        return "blocked", note or "ISO List 找不到對應圖號/檔名"
    if target in seen_targets:
        return "blocked", f"目標檔名重複：{target.name}"
    if target.exists() and target != source:
        return "blocked", f"目標已存在：{target.name}"
    if note:
        return "warn", note
    if new_name == source.name:
        return "idle", "檔名已相同"
    return "ready", ""


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "ready": sum(1 for row in rows if row["status"] == "ready"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "blocked": sum(1 for row in rows if row["status"] == "blocked"),
        "selected": sum(1 for row in rows if row["selected"]),
    }


def _default_export_path(request: IsoWorkflowRequest, rows: list[dict[str, Any]]) -> Path:
    folder = _default_export_folder(request, rows)
    return folder / f"iso_rename_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def _default_export_folder(request: IsoWorkflowRequest, rows: list[dict[str, Any]]) -> Path:
    for path in (
        request.page_folder,
        request.combine_pdf.parent if request.combine_pdf else None,
        request.work_folder,
        request.iso_list.parent if request.iso_list else None,
    ):
        if path is not None:
            return path if path.is_dir() else path.parent
    for row in rows:
        source = _path_or_none(row.get("source_path"))
        if source is not None:
            return source.parent
    return Path.cwd()


def _steps(source_kind: str, pdf_count: int, record_count: int, detect_serials: bool, summary: dict[str, int]) -> list[dict[str, str]]:
    split_state = "ready" if source_kind in {"combine_pdf", "existing_pages", "page_folder", "work_folder_pages"} and pdf_count else "blocked"
    detect_state = "ready" if detect_serials else "idle"
    plan_state = "blocked" if summary["blocked"] else "warn" if summary["warn"] else "ready"
    return [
        {"label": "來源", "state": "ready" if pdf_count else "blocked", "meta": f"{pdf_count} PDFs"},
        {"label": "拆頁", "state": split_state, "meta": source_kind},
        {"label": "ISO", "state": "ready" if record_count else "blocked", "meta": f"{record_count} rows"},
        {"label": "判讀", "state": detect_state, "meta": "enabled" if detect_serials else "page order"},
        {"label": "命名", "state": plan_state, "meta": f"{summary['selected']} selected"},
        {"label": "更名", "state": "idle", "meta": "manual apply"},
    ]


def _pdfs_from_folder(folder: Path) -> list[Path]:
    return sorted((path for path in folder.iterdir() if path.suffix.lower() == ".pdf"), key=natural_pdf_key)


def _auto_combine_pdf_candidate(folder: Path) -> Path | None:
    if not folder.exists() or not folder.is_dir():
        return None
    pdfs = _pdfs_from_folder(folder)
    if not pdfs:
        return None
    non_page_pdfs = [path for path in pdfs if not _looks_like_page_pdf(path)]
    if len(non_page_pdfs) == 1:
        return non_page_pdfs[0]
    if len(pdfs) == 1:
        return pdfs[0]
    scored = sorted(
        non_page_pdfs,
        key=lambda path: (
            30 if "combine" in path.stem.lower() else 0,
            20 if "合併" in path.stem else 0,
            path.stat().st_size,
            path.stat().st_mtime,
        ),
        reverse=True,
    )
    return scored[0] if scored else None


def _nearby_iso_list_candidates(request: IsoWorkflowRequest) -> list[Path]:
    candidates: list[Path] = []
    for root in _source_roots(request):
        for pattern in ("*.xlsx", "*.xlsm", "*.csv"):
            candidates.extend(path for path in root.glob(pattern) if not path.name.startswith("~$"))

    def score(path: Path) -> tuple[int, float]:
        name = path.stem.lower()
        value = 0
        for keyword, points in (
            ("iso", 40),
            ("圖號", 35),
            ("清單", 25),
            ("list", 20),
            ("dwg", 20),
            ("pdf_page_to_new_name", -80),
            ("rename_plan", -100),
        ):
            if keyword in name:
                value += points
        return value, path.stat().st_mtime

    unique = sorted(set(candidates), key=score, reverse=True)
    return [path for path in unique if score(path)[0] > -50]


def _source_roots(request: IsoWorkflowRequest) -> list[Path]:
    roots: list[Path] = []
    for path in (
        request.page_folder,
        request.combine_pdf.parent if request.combine_pdf else None,
        request.work_folder,
        request.iso_list.parent if request.iso_list else None,
    ):
        if path and path.exists():
            root = path if path.is_dir() else path.parent
            if root not in roots:
                roots.append(root)
    return roots


def _looks_like_page_pdf(path: Path) -> bool:
    stem = path.stem.casefold()
    return bool(
        re.search(r"(^|[_\-\s])(p|page|頁)\s*0*\d{1,4}$", stem)
        or re.search(r"(^|[_\-\s])0*\d{1,4}$", stem)
    )


def _normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": str(payload.get("action") or "plan"),
        "profile_folder": _path_or_none(payload.get("profile_folder")),
        "work_folder": _path_or_none(payload.get("work_folder")),
        "combine_pdf": _path_or_none(payload.get("combine_pdf")),
        "page_folder": _path_or_none(payload.get("page_folder")),
        "iso_list": _path_or_none(payload.get("iso_list")),
        "sheet_name": str(payload.get("sheet_name") or "").strip() or None,
        "serial_col": _int_or_none(payload.get("serial_col")),
        "line_col": _int_or_none(payload.get("line_col")),
        "pattern": str(payload.get("pattern") or "").strip() or None,
        "serial_region": _dict_or_none(payload.get("serial_region")),
        "drawing_region": _dict_or_none(payload.get("drawing_region")),
        "confidence_threshold": _float_or_none(payload.get("confidence_threshold")),
        "detect_serials": bool(payload.get("detect_serials")),
        "export_path": _path_or_none(payload.get("export_path")),
        "rows": tuple(payload.get("rows") or ()),
    }


def _path_or_none(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _state_store() -> AppStateStore:
    override = os.environ.get(STATE_PATH_ENV)
    return AppStateStore(Path(override)) if override else AppStateStore()


def _with_profile_defaults(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> tuple[IsoWorkflowRequest, dict[str, Any]]:
    folder, profile, candidates = _load_profile_for_request(request, resolved_page_folder=resolved_page_folder)
    if profile is None:
        return request, _profile_response(
            action="load_profile",
            folder=folder,
            profile=IsoNamingProfile(),
            exists=False,
            candidates=candidates,
            message="未套用既有 profile。",
        )

    updates: dict[str, Any] = {}
    if request.iso_list is None and profile.iso_list_path is not None and profile.iso_list_path.exists():
        updates["iso_list"] = profile.iso_list_path
    if request.sheet_name is None:
        updates["sheet_name"] = profile.sheet_name
    if request.serial_col is None:
        updates["serial_col"] = profile.serial_col
    if request.line_col is None:
        updates["line_col"] = profile.line_col
    if request.pattern is None or request.pattern == DEFAULT_PATTERN:
        updates["pattern"] = profile.pattern
    if request.serial_region is None:
        updates["serial_region"] = _region_payload(profile.serial_region)
    if request.drawing_region is None:
        updates["drawing_region"] = _region_payload(profile.drawing_region)
    if request.confidence_threshold is None:
        updates["confidence_threshold"] = profile.confidence_threshold
    return replace(request, **updates), _profile_response(
        action="load_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=candidates,
        message=f"已套用 ISO profile：{folder}",
    )


def _profile_folder(request: IsoWorkflowRequest) -> Path | None:
    return next(iter(_profile_folder_candidates(request)), None)


def _load_profile_for_request(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> tuple[Path | None, IsoNamingProfile | None, list[Path]]:
    candidates = _profile_folder_candidates(request, resolved_page_folder=resolved_page_folder)
    store = _state_store()
    for folder in candidates:
        profile = load_iso_naming_profile(store, folder)
        if profile is not None:
            return folder, profile, candidates
    return (candidates[0] if candidates else None), None, candidates


def _profile_folder_candidates(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> list[Path]:
    candidates: list[Path] = []

    def add_folder(path: Path | None) -> None:
        if path is None:
            return
        folder = path if _is_probable_folder(path) else path.parent
        if folder not in candidates:
            candidates.append(folder)

    def add_exact_folder(path: Path | None) -> None:
        if path is not None and path not in candidates:
            candidates.append(path)

    add_folder(request.profile_folder)
    add_exact_folder(request.page_folder)
    add_exact_folder(resolved_page_folder)
    if request.combine_pdf is not None:
        add_exact_folder(request.combine_pdf.with_name(f"{request.combine_pdf.stem}_pages"))
    if request.work_folder is not None:
        combine_candidate = _auto_combine_pdf_candidate(request.work_folder)
        if combine_candidate is not None:
            add_exact_folder(combine_candidate.with_name(f"{combine_candidate.stem}_pages"))
        add_existing_page_folders(request.work_folder, candidates)
    add_folder(request.work_folder)
    add_folder(request.combine_pdf.parent if request.combine_pdf else None)
    add_folder(request.iso_list.parent if request.iso_list else None)
    return candidates


def add_existing_page_folders(root: Path, candidates: list[Path]) -> None:
    if not root.exists() or not root.is_dir():
        return
    page_folders = sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.casefold().endswith("_pages")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for folder in page_folders:
        if folder not in candidates:
            candidates.append(folder)


def _is_probable_folder(path: Path) -> bool:
    if path.exists():
        return path.is_dir()
    return not path.suffix


def _profile_from_request(request: IsoWorkflowRequest, base: IsoNamingProfile) -> IsoNamingProfile:
    return IsoNamingProfile(
        serial_region=_region_from_payload(request.serial_region, base.serial_region),
        drawing_region=_region_from_payload(request.drawing_region, base.drawing_region),
        confidence_threshold=request.confidence_threshold if request.confidence_threshold is not None else base.confidence_threshold,
        pattern=_plan_pattern(request, base.pattern),
        iso_list_path=request.iso_list or base.iso_list_path,
        sheet_name=request.sheet_name or base.sheet_name,
        serial_col=request.serial_col if request.serial_col is not None else base.serial_col,
        line_col=request.line_col if request.line_col is not None else base.line_col,
    )


def _profile_response(
    *,
    action: str,
    folder: Path | None,
    profile: IsoNamingProfile,
    exists: bool,
    candidates: list[Path],
    message: str,
) -> dict[str, Any]:
    payload = profile.to_payload()
    discovery = _source_discovery(folder=folder, profile=profile)
    return {
        "schema_version": 1,
        "action": action,
        "created_at": _now(),
        "exists": exists,
        "folder": str(folder or ""),
        "folder_exists": bool(folder and folder.exists()),
        "candidate_folders": [str(candidate) for candidate in candidates],
        "serial_region": payload["serial_region"],
        "drawing_region": payload["drawing_region"],
        "confidence_threshold": payload["confidence_threshold"],
        "pattern": payload["pattern"],
        "iso_list_path": payload["iso_list_path"],
        "sheet_name": payload["sheet_name"],
        "serial_col": payload["serial_col"],
        "line_col": payload["line_col"],
        **discovery,
        "message": message,
    }


def _source_discovery(*, folder: Path | None, profile: IsoNamingProfile) -> dict[str, Any]:
    combine_pdf = _discover_combine_pdf(folder)
    page_folder = _discover_page_folder(folder, combine_pdf)
    iso_list = profile.iso_list_path if profile.iso_list_path is not None else _discover_iso_list(folder, combine_pdf, page_folder)
    return {
        "detected_combine_pdf": str(combine_pdf) if combine_pdf else None,
        "detected_page_folder": str(page_folder) if page_folder else None,
        "detected_page_folder_exists": bool(page_folder and page_folder.exists()),
        "detected_iso_list": str(iso_list) if iso_list else None,
    }


def _discover_combine_pdf(folder: Path | None) -> Path | None:
    if folder is None:
        return None
    if folder.name.casefold().endswith("_pages"):
        stem = folder.name[:-6]
        inferred = folder.parent / f"{stem}.pdf"
        if inferred.exists():
            return inferred
        return _auto_combine_pdf_candidate(folder.parent)
    return _auto_combine_pdf_candidate(folder)


def _discover_page_folder(folder: Path | None, combine_pdf: Path | None) -> Path | None:
    if folder is not None and folder.name.casefold().endswith("_pages"):
        return folder
    if combine_pdf is not None:
        return combine_pdf.with_name(f"{combine_pdf.stem}_pages")
    return None


def _discover_iso_list(folder: Path | None, combine_pdf: Path | None, page_folder: Path | None) -> Path | None:
    roots: list[Path] = []
    for path in (
        folder,
        combine_pdf.parent if combine_pdf else None,
        page_folder.parent if page_folder else None,
    ):
        if path and path.exists():
            root = path if path.is_dir() else path.parent
            if root not in roots:
                roots.append(root)
    candidates: list[Path] = []
    for root in roots:
        for pattern in ("*.xlsx", "*.xlsm", "*.csv"):
            candidates.extend(path for path in root.glob(pattern) if not path.name.startswith("~$"))
    return _best_iso_candidate(candidates)


def _best_iso_candidate(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None

    def score(path: Path) -> tuple[int, float]:
        name = path.stem.lower()
        value = 0
        for keyword, points in (
            ("iso", 40),
            ("圖號", 35),
            ("清單", 25),
            ("list", 20),
            ("dwg", 20),
            ("pdf_page_to_new_name", -80),
            ("rename_plan", -100),
        ):
            if keyword in name:
                value += points
        return value, path.stat().st_mtime

    scored = sorted(set(candidates), key=score, reverse=True)
    return scored[0] if scored and score(scored[0])[0] > -50 else None


def _plan_pattern(request: IsoWorkflowRequest, fallback: str = DEFAULT_PATTERN) -> str:
    return (request.pattern or fallback or DEFAULT_PATTERN).strip() or DEFAULT_PATTERN


def _region_from_payload(payload: dict[str, Any] | None, default: SerialVisionRegion) -> SerialVisionRegion:
    if not isinstance(payload, dict):
        return default
    return SerialVisionRegion(
        left=_float_value(payload.get("left"), default.left),
        top=_float_value(payload.get("top"), default.top),
        width=_float_value(payload.get("width"), default.width),
        height=_float_value(payload.get("height"), default.height),
    )


def _region_payload(region: SerialVisionRegion) -> dict[str, float]:
    return {
        "left": region.left,
        "top": region.top,
        "width": region.width,
        "height": region.height,
    }


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_stdin_json() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


def _resolve_sheet_name(path: Path, requested_sheet: str | None) -> tuple[str | None, list[str]]:
    sheets = list_iso_sheets(path)
    if requested_sheet:
        return requested_sheet, sheets
    if len(sheets) <= 1:
        return None, sheets
    return _preferred_sheet_name(path, sheets), sheets


def _preferred_sheet_name(path: Path, sheets: list[str]) -> str | None:
    scored = [(_score_iso_sheet(path, sheet), index, sheet) for index, sheet in enumerate(sheets)]
    scored.sort(reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][2]
    preferred_keywords = ("dwg", "iso", "isometric", "list", "管線", "清單", "圖號")
    for sheet in sheets:
        normalized = sheet.lower().replace(" ", "")
        if any(keyword in normalized for keyword in preferred_keywords):
            return sheet
    return sheets[0] if sheets else None


def _score_iso_sheet(path: Path, sheet_name: str) -> int:
    score = 0
    normalized_sheet = sheet_name.lower().replace(" ", "")
    if any(keyword in normalized_sheet for keyword in ("dwg", "iso", "圖號", "清單", "list")):
        score += 10
    try:
        table = read_iso_table(path, sheet_name=sheet_name)
    except Exception:
        return score
    serial_col, line_col = guess_iso_columns(table.headers)
    if serial_col is not None:
        score += 30
    if line_col is not None:
        score += 30
        header = table.headers[line_col].lower()
        if any(keyword in header for keyword in ("file_basename", "dst_pdf_name", "source_pdf_name", "pdf", "檔名", "圖號")):
            score += 50
    score += min(20, len(table.rows) // 10)
    return score


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class _SerialDetector:
    def __init__(self) -> None:
        self._app = None
        self._cache_dir = Path(tempfile.mkdtemp(prefix="tauri_iso_preview_"))

    def detect(self, source: Path, lookup: dict[str, IsoRecord]) -> SerialVisionResult:
        try:
            self._ensure_qt()
            from launcher.ui.iso_pdf.batch_detect import detect_serial_from_pdf

            return correct_result_with_iso_lookup(detect_serial_from_pdf(source, DEFAULT_SERIAL_REGION), lookup)
        except Exception as exc:
            return SerialVisionResult("", 0.0, f"影像判讀失敗：{exc}")

    def _ensure_qt(self) -> None:
        if self._app is not None:
            return
        from PyQt6.QtWidgets import QApplication

        self._app = QApplication.instance() or QApplication([])


if __name__ == "__main__":
    raise SystemExit(main())
