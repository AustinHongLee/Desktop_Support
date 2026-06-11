from __future__ import annotations

from typing import Any


def validate_one_click_plan(run_log: dict[str, Any], projection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(run_log.get("status") or "") != "completed":
        errors.append(f"workflow run status must be completed; got {run_log.get('status') or 'unknown'}")

    rows = projection.get("rows") if isinstance(projection.get("rows"), list) else []
    source = projection.get("source") if isinstance(projection.get("source"), dict) else {}
    pdf_count = _int_or_none(source.get("pdf_count"))
    if not rows:
        errors.append("rows must not be empty")
    if pdf_count is None:
        errors.append("source.pdf_count is required")
    elif len(rows) != pdf_count:
        errors.append(f"rows length must match source.pdf_count; got {len(rows)} rows and pdf_count {pdf_count}")

    selected_targets: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not row.get("selected"):
            continue
        target = str(row.get("target_path") or "").strip()
        if not target:
            errors.append(f"selected row {index} is missing target_path")
            continue
        if target in selected_targets:
            errors.append(f"selected target_path duplicated: {target}")
        selected_targets[target] = index

    expected_summary = _summary_from_rows(rows)
    summary = projection.get("summary") if isinstance(projection.get("summary"), dict) else {}
    for key, expected in expected_summary.items():
        actual = _int_or_none(summary.get(key))
        if actual != expected:
            errors.append(f"summary.{key} must be {expected}; got {summary.get(key)!r}")

    pilot_results = projection.get("pilot_results") if isinstance(projection.get("pilot_results"), list) else []
    if not pilot_results:
        errors.append("pilot_results must not be empty")
    elif not any(isinstance(item, dict) and item.get("id") == "P01" for item in pilot_results):
        errors.append("pilot_results must contain P01")

    return errors


def _summary_from_rows(rows: list[Any]) -> dict[str, int]:
    dict_rows = [row for row in rows if isinstance(row, dict)]
    return {
        "total": len(dict_rows),
        "ready": sum(1 for row in dict_rows if row.get("status") == "ready"),
        "warn": sum(1 for row in dict_rows if row.get("status") == "warn"),
        "blocked": sum(1 for row in dict_rows if row.get("status") == "blocked"),
        "selected": sum(1 for row in dict_rows if row.get("selected")),
    }


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
