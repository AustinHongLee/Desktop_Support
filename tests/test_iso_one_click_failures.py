from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, apply_iso_plan
from launcher.plugins.iso_tools.workflow.one_click_guard import validate_one_click_plan


ONE_CLICK_WORKFLOW_PATH = Path("launcher/plugins/iso_tools/workflow/workflows/iso_pdf_one_click.workflow.json")


def test_apply_record_lock_downgrades_to_warning_after_rename(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DESKTOP_SUPPORT_ISO_RUN_ROOT", str(tmp_path / "iso_runs"))
    source = tmp_path / "page_001.pdf"
    target = tmp_path / "1--PIPE-A.pdf"
    source.write_bytes(b"%PDF-1.4\n")

    with patch("launcher.app.tauri_iso_workflow._record_apply_csv", side_effect=PermissionError(13, "locked")):
        payload = apply_iso_plan(_apply_request(source, target, run_id="record-lock"))

    assert payload["renamed_count"] == 1
    assert "record_path" not in payload
    assert payload["record_warning"]["path"].endswith("apply_rename_record.csv")
    assert "記錄檔被佔用" in payload["record_warning"]["message"]
    assert not source.exists()
    assert target.exists()


def test_locked_pdf_apply_error_is_actionable(tmp_path) -> None:
    source = tmp_path / "page_001.pdf"
    target = tmp_path / "1--PIPE-A.pdf"
    source.write_bytes(b"%PDF-1.4\n")

    with patch(
        "launcher.app.tauri_iso_workflow._apply_operations",
        side_effect=PermissionError(13, "locked", str(source)),
    ):
        with pytest.raises(ValueError, match=r"PDF 正被其他程式開啟.*page_001\.pdf.*已完成 0 筆，未動 1 筆"):
            apply_iso_plan(_apply_request(source, target, run_id="pdf-lock"))

    assert source.exists()
    assert not target.exists()


def test_one_click_graph_batch_detect_timeout_is_1800_seconds() -> None:
    graph = json.loads(ONE_CLICK_WORKFLOW_PATH.read_text(encoding="utf-8"))
    nodes = {node["node_id"]: node for node in graph["nodes"]}

    assert nodes["batch_detect"]["params"]["timeout_s"] == 1800


def test_completed_with_blocked_is_rejected_before_one_click_projection_can_apply() -> None:
    errors = validate_one_click_plan(
        {"status": "completed_with_blocked"},
        {
            "source": {"pdf_count": 1},
            "summary": {"total": 1, "ready": 1, "warn": 0, "blocked": 0, "selected": 1},
            "rows": [
                {
                    "id": "row-1",
                    "source_path": "C:/work/page_001.pdf",
                    "target_path": "C:/work/1--PIPE-A.pdf",
                    "selected": True,
                }
            ],
            "pilot_results": [{"id": "P01"}],
        },
    )

    assert any("status must be completed" in error for error in errors)


def test_frontend_one_click_failure_copy_exposes_manual_fallback_and_node_messages() -> None:
    text = "\n".join(
        [
            Path("frontend/tauri-spike/src/iso/IsoBoard.tsx").read_text(encoding="utf-8"),
            Path("frontend/tauri-spike/src/iso/AutopilotView.tsx").read_text(encoding="utf-8"),
            Path("frontend/tauri-spike/src/iso/components/FailureCard.tsx").read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "改用傳統路徑重跑",
        "PDF 拆頁失敗",
        "ISO 清單讀取失敗",
        "流水號辨識失敗",
        "命名檢查未通過",
    ):
        assert phrase in text


def _apply_request(source: Path, target: Path, *, run_id: str) -> IsoWorkflowRequest:
    return IsoWorkflowRequest(
        action="apply",
        run_id=run_id,
        rows=(
            {
                "id": "row-1",
                "page": 1,
                "source_path": str(source),
                "source_name": source.name,
                "serial": "1",
                "line_no": "PIPE-A",
                "new_name": target.name,
                "target_path": str(target),
                "status": "ready",
                "selected": True,
                "confidence": 1.0,
            },
        ),
    )
