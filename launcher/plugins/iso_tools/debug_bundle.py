from __future__ import annotations

import csv
import io
import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.run_log import iso_run_root


def export_iso_debug_bundle(run_id: str, export_path: Path | None = None) -> dict[str, Any]:
    safe_run_id = _safe_run_id(run_id)
    if not safe_run_id:
        raise ValueError("缺少 run_id，無法匯出 ISO 問題包。")

    run_dir = iso_run_root() / safe_run_id
    run_json = run_dir / "run.json"
    if not run_json.exists():
        raise FileNotFoundError(f"找不到 ISO run log：{safe_run_id}")

    run_payload = json.loads(run_json.read_text(encoding="utf-8"))
    bundle_path = export_path or run_dir / f"iso_debug_{safe_run_id}.zip"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    included: list[str] = []
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        included.extend(_write_file_if_exists(archive, run_json, "run.json"))
        included.extend(_write_file_if_exists(archive, run_dir / "events.jsonl", "events.jsonl"))
        included.extend(_write_plan_csv(archive, run_payload, run_dir / "plan.csv"))
        archive.writestr("pilot.json", json.dumps(run_payload.get("pilot_results") or [], ensure_ascii=False, indent=2))
        included.append("pilot.json")
        archive.writestr("profile.json", json.dumps(run_payload.get("profile") or {}, ensure_ascii=False, indent=2))
        included.append("profile.json")
        archive.writestr("env.json", json.dumps(_env_summary(), ensure_ascii=False, indent=2))
        included.append("env.json")
        archive.writestr("README.txt", _readme_text(run_payload))
        included.append("README.txt")

    return {
        "schema_version": 1,
        "action": "export_debug_bundle",
        "created_at": _now(),
        "run_id": safe_run_id,
        "export_path": str(bundle_path),
        "included_files": included,
        "message": f"已匯出 ISO 問題包：{bundle_path}",
    }


def _write_file_if_exists(archive: zipfile.ZipFile, path: Path, arcname: str) -> list[str]:
    if not path.exists():
        return []
    archive.write(path, arcname)
    return [arcname]


def _write_plan_csv(archive: zipfile.ZipFile, run_payload: dict[str, Any], path: Path) -> list[str]:
    if path.exists():
        archive.write(path, "plan.csv")
        return ["plan.csv"]
    rows = run_payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return []
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
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        if isinstance(row, dict):
            writer.writerow({column: row.get(column, "") for column in columns})
    archive.writestr("plan.csv", buffer.getvalue())
    return ["plan.csv"]


def _env_summary() -> dict[str, Any]:
    return {
        "created_at": _now(),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "run_root": str(iso_run_root()),
        "contains_original_pdf_or_xlsx": False,
    }


def _readme_text(run_payload: dict[str, Any]) -> str:
    failure = run_payload.get("failure") or {}
    return "\n".join(
        [
            "ISO PDF debug bundle",
            "",
            f"Run ID: {run_payload.get('run_id', '')}",
            f"Status: {run_payload.get('status', '')}",
            f"Action: {run_payload.get('action', '')}",
            f"Failed stage: {failure.get('failed_stage', '')}",
            f"Summary: {failure.get('user_summary', '')}",
            "",
            "This bundle intentionally excludes original PDF/XLSX files.",
            "Share this zip with an engineer together with the failing work folder context.",
            "",
        ]
    )


def _safe_run_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "", value or "")[:96]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
