from __future__ import annotations

from importlib import import_module
from typing import Any


def build_request(payload: dict[str, Any]) -> Any:
    backend = _backend()
    return backend.IsoWorkflowRequest(**backend._normalize_request(dict(payload)))


def discover_sources(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("discover_sources", payload, "discover_sources")


def load_iso_table(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("load_iso_table", payload, "load_iso_table")


def split_iso_pdf(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("split_pdf", payload, "split_iso_pdf")


def load_iso_profile(payload: dict[str, Any], *, prefer_draft: bool = False) -> dict[str, Any]:
    backend = _backend()
    request = build_request({"action": "load_profile", **payload})
    if not prefer_draft:
        return backend.load_iso_profile(request)

    folder = backend._profile_folder(request)
    if folder is None:
        return backend.load_iso_profile(request)
    draft = backend.load_iso_naming_profile_draft(backend._state_store(), folder)
    if draft is None:
        return backend.load_iso_profile(request)
    return backend._profile_response(
        action="load_profile",
        folder=folder,
        profile=draft,
        exists=True,
        candidates=backend._profile_folder_candidates(request),
        message=f"已載入草稿資料夾設定：{folder}",
        profile_scope="draft",
    )


def build_iso_plan(payload: dict[str, Any], *, as_rename_plan: bool = False) -> dict[str, Any]:
    action = "build_rename_plan" if as_rename_plan else "plan"
    function_name = "build_rename_plan" if as_rename_plan else "build_iso_plan"
    return _call(action, payload, function_name)


def pilot_report(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("pilot_report", payload, "pilot_report")


def roi_distribution(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("roi_distribution", payload, "roi_distribution")


def export_plan_csv(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("export_plan_csv", payload, "export_plan_csv")


def export_debug_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("export_debug_bundle", payload, "export_debug_bundle")


def start_batch_detect(payload: dict[str, Any]) -> dict[str, Any]:
    return _call("start_batch_detect", payload, "start_batch_detect")


def iso_job_status(job_id: str) -> dict[str, Any]:
    return _call("job_status", {"job_id": job_id}, "iso_job_status")


def cancel_iso_job(job_id: str) -> dict[str, Any]:
    return _call("cancel_job", {"job_id": job_id}, "cancel_iso_job")


def predict_split_pdf(payload: dict[str, Any]) -> dict[str, Any]:
    request = build_request({"action": "split_pdf", **payload})
    backend = _backend()
    if request.page_folder is not None:
        return {
            "would_write": False,
            "source_kind": "page_folder",
            "page_folder": str(request.page_folder),
            "reason": "page_folder input supplied",
        }

    combine_pdf = request.combine_pdf
    if combine_pdf is None and request.work_folder is not None:
        combine_pdf = backend._auto_combine_pdf_candidate(request.work_folder)
        if combine_pdf is None:
            pdfs = backend._pdfs_from_folder(request.work_folder) if request.work_folder.exists() and request.work_folder.is_dir() else []
            return {
                "would_write": False,
                "source_kind": "work_folder_pages" if pdfs else "missing_source",
                "page_folder": str(request.work_folder) if pdfs else "",
                "reason": "work_folder pages" if pdfs else "no combine pdf discovered",
            }

    if combine_pdf is None:
        return {"would_write": False, "source_kind": "missing_source", "page_folder": "", "reason": "no combine_pdf"}

    page_folder = combine_pdf.with_name(f"{combine_pdf.stem}_pages")
    if page_folder.exists() and backend._pdfs_from_folder(page_folder):
        return {
            "would_write": False,
            "source_kind": "existing_pages",
            "page_folder": str(page_folder),
            "reason": "existing split pages",
        }
    return {
        "would_write": True,
        "source_kind": "combine_pdf",
        "page_folder": str(page_folder),
        "combine_pdf": str(combine_pdf),
        "reason": "combine pdf needs split",
    }


def profile_from_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": payload.get("profile_scope") or "published",
        "exists": bool(payload.get("exists")),
        "published_exists": bool(payload.get("published_exists")),
        "draft_exists": bool(payload.get("draft_exists")),
        "history_count": payload.get("history_count") or 0,
        "serial_region": payload.get("serial_region"),
        "drawing_region": payload.get("drawing_region"),
        "confidence_threshold": payload.get("confidence_threshold"),
        "pattern": payload.get("pattern"),
        "iso_list_path": payload.get("iso_list_path"),
        "sheet_name": payload.get("sheet_name"),
        "serial_col": payload.get("serial_col"),
        "line_col": payload.get("line_col"),
    }


def source_candidates_from_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_folders": payload.get("candidate_folders") or [],
        "detected_combine_pdf": payload.get("detected_combine_pdf"),
        "detected_page_folder": payload.get("detected_page_folder"),
        "detected_page_folder_exists": bool(payload.get("detected_page_folder_exists")),
        "detected_iso_list": payload.get("detected_iso_list"),
        "message": payload.get("message") or "",
    }


def _call(action: str, payload: dict[str, Any], function_name: str) -> dict[str, Any]:
    backend = _backend()
    request = build_request({"action": action, **payload})
    return getattr(backend, function_name)(request)


def _backend() -> Any:
    return import_module("launcher.app.tauri_iso_workflow")
