from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow.parity import list_parity_reports

GATE_WINDOW = 5
GATE_MIN_REAL = 2
POLLUTION_COMMAND = "python -m pytest tests/test_iso_workflow_pollution.py tests/test_frontend_safety_contract.py -q"
DESIGN_DOC = Path("docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md")


def evaluate_switchover_gate(
    *,
    reports: list[dict[str, Any]] | None = None,
    design_path: Path = DESIGN_DOC,
) -> dict[str, Any]:
    source_reports = reports if reports is not None else list_parity_reports(limit=GATE_WINDOW)["reports"]
    window = list(source_reports)[:GATE_WINDOW]
    equal_count = sum(1 for report in window if _is_equal_report(report))
    real_count = sum(1 for report in window if str(report.get("sample_kind") or "unknown") == "real")
    enough_reports = len(window) >= GATE_WINDOW
    all_equal = enough_reports and equal_count == GATE_WINDOW
    enough_real = real_count >= GATE_MIN_REAL
    design_exists = design_path.exists()
    conditions = [
        {
            "id": "recent_all_equal",
            "title": "最近 5 筆 parity 全一致",
            "met": all_equal,
            "detail": "已達成" if all_equal else f"目前 {len(window)}/{GATE_WINDOW} 筆，equal {equal_count}/{GATE_WINDOW} 筆。",
        },
        {
            "id": "real_samples",
            "title": "最近 5 筆至少 2 筆 real sample",
            "met": enough_real,
            "detail": "已達成" if enough_real else f"目前 real sample {real_count}/{GATE_MIN_REAL} 筆；fixture/unknown 不計入。",
        },
        {
            "id": "pollution_suite",
            "title": "防污染與前端安全契約綠燈",
            "met": None,
            "detail": POLLUTION_COMMAND,
        },
        {
            "id": "shadow_design",
            "title": "Shadow run 設計書已入庫",
            "met": design_exists,
            "detail": str(design_path),
        },
    ]
    ready = all_equal and enough_real and design_exists
    met_count = sum(1 for condition in conditions if condition["met"] is True)
    return {
        "schema_version": 1,
        "action": "workflow_switchover_gate",
        "ready": ready,
        "headline": "可進入 E 期換軌評估" if ready else f"尚未可換軌（{met_count}/4）",
        "conditions": conditions,
        "window": window,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _is_equal_report(report: dict[str, Any]) -> bool:
    return bool(report.get("equal")) and int(report.get("violation_count") or 0) == 0
