from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    _one_click_engine_path,
    _one_click_graph_hash,
    _workflow_job_dir,
    _write_json,
    workflow_one_click_engine_action,
    workflow_run_action,
    workflow_set_one_click_engine_action,
)
from launcher.core.paths import PROJECT_ROOT_ENV


def test_enable_one_click_engine_requires_ready_gate(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    with patch(
        "launcher.plugins.iso_tools.workflow.gate.evaluate_switchover_gate",
        return_value=_gate(False),
    ):
        with pytest.raises(ValueError, match="gate 未通過"):
            workflow_set_one_click_engine_action(
                IsoWorkflowRequest(action="workflow_set_one_click_engine", workflow={"engine": "workflow"})
            )

    assert not _one_click_engine_path().exists()


def test_enable_disable_one_click_engine_writes_flag_and_audit(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    with patch(
        "launcher.plugins.iso_tools.workflow.gate.evaluate_switchover_gate",
        return_value=_gate(True),
    ):
        enabled = workflow_set_one_click_engine_action(
            IsoWorkflowRequest(action="workflow_set_one_click_engine", workflow={"engine": "workflow"})
        )
    disabled = workflow_set_one_click_engine_action(
        IsoWorkflowRequest(action="workflow_set_one_click_engine", workflow={"engine": "legacy", "reason": "test"})
    )
    flag = json.loads(_one_click_engine_path().read_text(encoding="utf-8"))
    audit = _audit_events(tmp_path)

    assert enabled["engine"] == "workflow"
    assert enabled["enabled"] is True
    assert enabled["graph_hash"] == _one_click_graph_hash()
    assert disabled["engine"] == "legacy"
    assert disabled["enabled"] is False
    assert flag["engine"] == "legacy"
    assert [event["event"] for event in audit] == ["enable", "disable"]


def test_one_click_workflow_run_is_locked_to_graph_and_safe_policy(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    _write_json(
        _one_click_engine_path(),
        {"schema_version": 1, "engine": "workflow", "graph_hash": _one_click_graph_hash(), "enabled_at": "test"},
    )
    monkeypatch.setattr("launcher.app.tauri_iso_workflow._spawn_workflow_job", lambda _job_dir: None)

    job = workflow_run_action(
        IsoWorkflowRequest(
            action="workflow_run",
            workflow={"one_click": True},
            workflow_inputs={"work_folder": "C:/work", "combine_pdf": "C:/work/combine.pdf"},
            workflow_allow=("renames_files",),
            workflow_confirm=("apply",),
            workflow_job_id="one-click-job",
        )
    )
    request = json.loads((_workflow_job_dir("one-click-job") / "request.json").read_text(encoding="utf-8"))

    assert job["workflow_job_id"] == "one-click-job"
    assert request["workflow_path"].endswith("iso_pdf_one_click.workflow.json")
    assert request["workflow"] is None
    assert request["workflow_allow"] == []
    assert request["workflow_confirm"] == []
    assert request["one_click"]["graph_hash"] == _one_click_graph_hash()


def test_one_click_workflow_run_rejects_graph_hash_mismatch(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    _write_json(
        _one_click_engine_path(),
        {"schema_version": 1, "engine": "workflow", "graph_hash": "sha256:wrong", "enabled_at": "test"},
    )

    with pytest.raises(ValueError, match="一鍵圖已被修改"):
        workflow_run_action(IsoWorkflowRequest(action="workflow_run", workflow={"one_click": True}))


def test_one_click_engine_auto_reverts_after_two_failures(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    _write_json(
        _one_click_engine_path(),
        {"schema_version": 1, "engine": "workflow", "graph_hash": _one_click_graph_hash(), "enabled_at": "test"},
    )
    _write_one_click_job("failed-1", "failed", "failed", "2026-06-11T08:00:00")
    _write_one_click_job("failed-2", "failed", "failed", "2026-06-11T08:01:00")

    engine = workflow_one_click_engine_action(IsoWorkflowRequest(action="workflow_one_click_engine"))
    audit = _audit_events(tmp_path)

    assert engine["engine"] == "legacy"
    assert engine["auto_reverted"] is True
    assert json.loads(_one_click_engine_path().read_text(encoding="utf-8"))["engine"] == "legacy"
    assert audit[-1]["event"] == "auto_revert"


def test_one_click_engine_does_not_count_cancelled_jobs_for_breaker(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    _write_json(
        _one_click_engine_path(),
        {"schema_version": 1, "engine": "workflow", "graph_hash": _one_click_graph_hash(), "enabled_at": "test"},
    )
    _write_one_click_job("failed-1", "failed", "failed", "2026-06-11T08:00:00")
    _write_one_click_job("cancelled-1", "cancelled", "cancelled", "2026-06-11T08:01:00")

    engine = workflow_one_click_engine_action(IsoWorkflowRequest(action="workflow_one_click_engine"))

    assert engine["engine"] == "workflow"
    assert engine["auto_reverted"] is False


def _redirect_runtime(monkeypatch, root: Path) -> None:
    monkeypatch.setenv(PROJECT_ROOT_ENV, str(root))
    monkeypatch.setenv("DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT", str(root / ".runtime" / "jobs" / "workflow"))
    monkeypatch.setenv("DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT", str(root / ".runtime" / "runs" / "workflow"))


def _gate(ready: bool) -> dict[str, object]:
    return {
        "schema_version": 1,
        "action": "workflow_switchover_gate",
        "ready": ready,
        "headline": "ready" if ready else "not ready",
        "conditions": [
            {"id": "recent_all_equal", "title": "最近 5 筆 parity 全一致", "met": ready, "detail": "test"},
        ],
        "window": [],
        "evaluated_at": "test",
    }


def _write_one_click_job(job_id: str, state: str, result_status: str, updated_at: str) -> None:
    job_dir = _workflow_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    _write_json(job_dir / "request.json", {"action": "workflow_run", "one_click": {"graph_hash": _one_click_graph_hash()}})
    _write_json(
        job_dir / "job.json",
        {
            "schema_version": 1,
            "action": "workflow_job",
            "workflow_job_id": job_id,
            "job_id": job_id,
            "state": state,
            "created_at": updated_at,
            "updated_at": updated_at,
            "result": {"status": result_status},
        },
    )


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / ".runtime" / "runs" / "engine_audit.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
