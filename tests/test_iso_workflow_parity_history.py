from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, workflow_parity_history_action
from launcher.core.paths import PROJECT_ROOT_ENV
from launcher.plugins.iso_tools.workflow.cli import main as workflow_cli_main
from launcher.plugins.iso_tools.workflow.parity import ParityReport, list_parity_reports, write_parity_report


def test_parity_reports_default_to_runtime_history_and_list_newest_first() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / "project"
        with patch.dict("os.environ", {PROJECT_ROOT_ENV: str(project_root)}):
            older = write_parity_report(ParityReport(equal=True), inputs={"sample": "older"})
            newer = write_parity_report(ParityReport(equal=False, violations=[{"field": "rows.serial"}]), inputs={"sample": "newer"})
            _set_created_at(older, "2026-06-10T00:00:00")
            _set_created_at(newer, "2026-06-10T00:00:01")
            history = list_parity_reports(limit=5)

    assert older.is_relative_to(project_root / ".runtime" / "runs" / "parity")
    assert newer.is_relative_to(project_root / ".runtime" / "runs" / "parity")
    assert history["report_count"] == 2
    assert history["reports"][0]["report_path"] == str(newer)
    assert history["reports"][0]["violation_count"] == 1
    assert history["reports"][0]["trigger"] == "cli"
    assert history["reports"][0]["sample_kind"] == "unknown"
    assert history["reports"][1]["equal"] is True


def test_cli_parity_history_lists_reports_as_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "parity"
        report_path = root / "20260610_000000_test" / "report.json"
        write_parity_report(ParityReport(equal=True), path=report_path, inputs={"sample": "fixture"}, sample_kind="fixture")

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = workflow_cli_main(["parity-history", "--root", str(root), "--json"])
        payload = json.loads(stdout.getvalue())

    assert exit_code == 0
    assert payload["action"] == "workflow_parity_history"
    assert payload["reports"][0]["report_path"] == str(report_path)
    assert payload["reports"][0]["inputs_digest"].startswith("sha256:")
    assert payload["reports"][0]["sample_kind"] == "fixture"


def test_tauri_action_reads_parity_history_without_writing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / "project"
        with patch.dict("os.environ", {PROJECT_ROOT_ENV: str(project_root)}):
            report_path = write_parity_report(ParityReport(equal=True), inputs={"sample": "tauri"})
            payload = workflow_parity_history_action(IsoWorkflowRequest(action="workflow_parity_history"))

    assert payload["reports"][0]["report_path"] == str(report_path)
    assert payload["reports"][0]["equal"] is True


def _set_created_at(path: Path, created_at: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = created_at
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
