from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, workflow_set_shadow_flag_action, workflow_switchover_gate_action
from launcher.core.paths import PROJECT_ROOT_ENV
from launcher.plugins.iso_tools.workflow.cli import main as workflow_cli_main
from launcher.plugins.iso_tools.workflow.gate import evaluate_switchover_gate
from launcher.plugins.iso_tools.workflow.parity import ParityReport, write_parity_report


def test_gate_ready_with_five_equal_and_two_real() -> None:
    payload = evaluate_switchover_gate(reports=[*_reports(3, sample_kind="fixture"), *_reports(2, sample_kind="real")], design_path=Path(__file__))

    assert payload["ready"] is True
    assert payload["conditions"][0]["met"] is True
    assert payload["conditions"][1]["met"] is True


def test_gate_not_ready_when_report_count_is_short() -> None:
    payload = evaluate_switchover_gate(reports=_reports(4, sample_kind="real"), design_path=Path(__file__))

    assert payload["ready"] is False
    assert payload["conditions"][0]["met"] is False
    assert "4/5" in payload["conditions"][0]["detail"]


def test_gate_not_ready_when_real_sample_count_is_short() -> None:
    payload = evaluate_switchover_gate(reports=[*_reports(4, sample_kind="fixture"), *_reports(1, sample_kind="real")], design_path=Path(__file__))

    assert payload["ready"] is False
    assert payload["conditions"][1]["met"] is False
    assert "1/2" in payload["conditions"][1]["detail"]


def test_gate_not_ready_when_any_recent_report_has_violation() -> None:
    reports = _reports(5, sample_kind="real")
    reports[2]["equal"] = False
    reports[2]["violation_count"] = 1

    payload = evaluate_switchover_gate(reports=reports, design_path=Path(__file__))

    assert payload["ready"] is False
    assert payload["conditions"][0]["met"] is False


def test_gate_treats_v1_unknown_reports_as_not_real() -> None:
    reports = _reports(5, sample_kind="unknown")

    payload = evaluate_switchover_gate(reports=reports, design_path=Path(__file__))

    assert payload["ready"] is False
    assert payload["conditions"][0]["met"] is True
    assert payload["conditions"][1]["met"] is False


def test_cli_gate_exit_code_seven_when_not_ready() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / "project"
        with patch.dict("os.environ", {PROJECT_ROOT_ENV: str(project_root)}):
            write_parity_report(ParityReport(equal=True), inputs={"sample": "fixture"}, sample_kind="fixture")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = workflow_cli_main(["gate", "--json"])
            payload = json.loads(stdout.getvalue())

    assert exit_code == 7
    assert payload["action"] == "workflow_switchover_gate"
    assert payload["ready"] is False


def test_tauri_gate_action_reports_shadow_flag_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / "project"
        with patch.dict("os.environ", {PROJECT_ROOT_ENV: str(project_root)}):
            off = workflow_switchover_gate_action(IsoWorkflowRequest(action="workflow_switchover_gate"))
            workflow_set_shadow_flag_action(IsoWorkflowRequest(action="workflow_set_shadow_flag", workflow={"enabled": True}))
            on = workflow_switchover_gate_action(IsoWorkflowRequest(action="workflow_switchover_gate"))

    assert off["shadow_flag_enabled"] is False
    assert on["shadow_flag_enabled"] is True


def _reports(count: int, *, sample_kind: str) -> list[dict[str, object]]:
    return [
        {
            "created_at": f"2026-06-10T00:00:{index:02d}",
            "equal": True,
            "violation_count": 0,
            "acceptable_diff_count": 0,
            "sample_kind": sample_kind,
            "trigger": "shadow" if sample_kind == "real" else "cli",
        }
        for index in range(count)
    ]
