from __future__ import annotations

import json
import os
from pathlib import Path

from openpyxl import Workbook
from pypdf import PdfWriter

from launcher.app import tauri_iso_worker
from launcher.core.paths import PROJECT_ROOT_ENV, STATE_PATH_ENV


def test_worker_throttles_full_rows_for_120_pages(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    sample = _sample_workspace(tmp_path / "work", pages=120)
    job_dir = tmp_path / "runtime" / "jobs" / "iso" / "large-job"
    _write_job_request(job_dir, sample, job_id="large-job")
    snapshots: list[tuple[str, int, int]] = []
    real_write_json = tauri_iso_worker._write_json

    def capture_progress(path: Path, payload: dict[str, object]) -> None:
        if path.name == "job.json":
            progress = payload.get("progress") if isinstance(payload, dict) else {}
            result = payload.get("result") if isinstance(payload, dict) else {}
            result_rows = result.get("rows") if isinstance(result, dict) else []
            snapshots.append(
                (
                    str(payload.get("state") or ""),
                    int(progress.get("done") or 0) if isinstance(progress, dict) else 0,
                    len(result_rows) if isinstance(result_rows, list) else 0,
                )
            )
        real_write_json(path, payload)

    monkeypatch.setattr(tauri_iso_worker, "_write_json", capture_progress)
    job = tauri_iso_worker.run_job(job_dir)
    progress_steps = {done for _state, done, _rows_len in snapshots}
    full_current_writes = [
        (state, done, rows_len)
        for state, done, rows_len in snapshots
        if done > 0 and rows_len == done
    ]

    assert job["state"] == "completed"
    assert len(job["rows"]) == 120
    assert job["progress"]["done"] == 120
    assert set(range(1, 121)).issubset(progress_steps)
    assert len(full_current_writes) <= 26
    assert len(full_current_writes) < 120
    assert full_current_writes[-1] == ("completed", 120, 120)


def test_worker_cancel_remains_next_page_responsive(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    sample = _sample_workspace(tmp_path / "work", pages=8)
    job_dir = tmp_path / "runtime" / "jobs" / "iso" / "cancel-job"
    _write_job_request(job_dir, sample, job_id="cancel-job")
    real_build_plan_rows = tauri_iso_worker._build_plan_rows
    calls = 0

    def build_once_then_cancel(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal calls
        result = real_build_plan_rows(*args, **kwargs)
        calls += 1
        if calls == 1:
            _write_json(job_dir / "cancel.json", {"cancelled_at": "test"})
        return result

    monkeypatch.setattr(tauri_iso_worker, "_build_plan_rows", build_once_then_cancel)
    job = tauri_iso_worker.run_job(job_dir)
    disk_job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))

    assert calls == 1
    assert job["state"] == "cancelled"
    assert job["progress"]["done"] == 1
    assert len(job["rows"]) == 1
    assert disk_job["state"] == "cancelled"
    assert len(disk_job["rows"]) == 1


def _sample_workspace(folder: Path, *, pages: int) -> Path:
    folder.mkdir(parents=True)
    page_folder = folder / "pages"
    page_folder.mkdir()
    for index in range(1, pages + 1):
        _write_pdf(page_folder / f"page_{index:03}.pdf", pages=1)
    _write_iso_list(folder / "iso_list.xlsx", rows=pages)
    return folder


def _write_job_request(job_dir: Path, sample: Path, *, job_id: str) -> None:
    job_dir.mkdir(parents=True)
    _write_json(
        job_dir / "request.json",
        {
            "action": "start_batch_detect",
            "work_folder": str(sample),
            "page_folder": str(sample / "pages"),
            "iso_list": str(sample / "iso_list.xlsx"),
            "sheet_name": "ISO",
            "serial_col": 0,
            "line_col": 1,
            "pattern": "{serial}--{line}.pdf",
            "detect_serials": False,
            "job_id": job_id,
            "run_id": job_id,
        },
    )
    _write_json(job_dir / "job.json", _job_payload(job_id))


def _redirect_runtime(monkeypatch, root: Path) -> None:
    monkeypatch.setenv(PROJECT_ROOT_ENV, str(root / "project_root"))
    monkeypatch.setenv(STATE_PATH_ENV, str(root / "state.json"))
    monkeypatch.setenv("DESKTOP_SUPPORT_JOB_ROOT", str(root / "runtime" / "jobs" / "iso"))
    monkeypatch.setenv("DESKTOP_SUPPORT_ISO_RUN_ROOT", str(root / "runtime" / "runs" / "iso"))


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_iso_list(path: Path, *, rows: int) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    for index in range(1, rows + 1):
        sheet.append([str(index), f"PIPE-{index:03}"])
    workbook.save(path)


def _job_payload(job_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "action": "batch_detect_job",
        "job_id": job_id,
        "state": "queued",
        "created_at": "test",
        "updated_at": "test",
        "progress": {"total": 0, "done": 0, "percent": 0},
        "rows": [],
        "issues": [],
        "events": [],
        "result": None,
        "error": "",
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
