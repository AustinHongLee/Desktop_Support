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
