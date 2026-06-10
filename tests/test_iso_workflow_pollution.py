from __future__ import annotations

import json
import os
import time
from pathlib import Path

from launcher.app import tauri_iso_worker, tauri_iso_workflow, tauri_workflow_job
from launcher.app.tauri_iso_workflow import IsoWorkflowRequest
from launcher.core.paths import PROJECT_ROOT_ENV, STATE_PATH_ENV
from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_workflow
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES, WRITES_CSV, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.projection import plan_from_run
from launcher.plugins.iso_tools.workflow.schema import load_workflow, normalize_graph
from tests.test_tauri_iso_workflow import _job_payload, _write_iso_list, _write_json, _write_pdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_WORKFLOW_PATH = PROJECT_ROOT / "launcher" / "plugins" / "iso_tools" / "workflow" / "workflows" / "iso_pdf_safe_poc.workflow.json"


def test_safe_run_x10_no_csv_pollution(tmp_path, monkeypatch) -> None:
    sample = _sample_workspace(tmp_path / "work", pages=2)
    _redirect_runtime(monkeypatch, tmp_path)
    _patch_sync_iso_worker(monkeypatch)
    run_dirs: list[Path] = []

    for _index in range(10):
        result = _run_safe_poc(tmp_path, sample)
        assert result["status"] == "completed"
        run_dirs.append(Path(result["run_dir"]))

    assert len(set(run_dirs)) == 10
    assert all((run_dir / "run_log.json").exists() for run_dir in run_dirs)
    assert _csvs_under(sample) == []
    assert _rename_plan_csvs_under(sample) == []


def test_apply_writes_record_artifact_only(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    source = tmp_path / "work" / "page_001.pdf"
    target = tmp_path / "work" / "1--PIPE-A.pdf"
    source.parent.mkdir()
    _write_pdf(source, pages=1)

    payload = tauri_iso_workflow.apply_iso_plan(
        IsoWorkflowRequest(
            action="apply",
            run_id="iso-apply-record",
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
    )
    record_path = Path(str(payload["record_path"]))

    assert payload["renamed_count"] == 1
    assert payload["record_row_count"] == 1
    assert record_path.exists()
    assert record_path.is_relative_to(tmp_path / "runtime" / "runs" / "iso")
    assert source.exists() is False
    assert target.exists() is True
    assert _rename_plan_csvs_under(tmp_path / "work") == []


def test_workflow_apply_keeps_workdir_clean(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    source = tmp_path / "work" / "page_001.pdf"
    target = tmp_path / "work" / "101--PIPE-A.pdf"
    source.parent.mkdir()
    _write_pdf(source, pages=1)

    result = run_workflow(
        normalize_graph(_apply_graph()),
        inputs={"rows": [_row(source, target)]},
        run_root=tmp_path / "runtime" / "runs" / "workflow",
        policy=SideEffectPolicy(
            allowed_guarded=frozenset({RENAMES_FILES}),
            confirmed_nodes=frozenset({"apply"}),
        ),
    )

    assert result["status"] == "completed"
    assert source.exists() is False
    assert target.exists() is True
    assert _csvs_under(tmp_path / "work") == []


def test_replay_blocks_csv_even_with_policy_flags(tmp_path, monkeypatch) -> None:
    sample = _sample_workspace(tmp_path / "work", pages=1)
    _redirect_runtime(monkeypatch, tmp_path)
    _patch_sync_iso_worker(monkeypatch)
    graph = _safe_graph_with_export_enabled()

    source = run_workflow(
        graph,
        inputs=_safe_inputs(sample),
        run_root=tmp_path / "runtime" / "runs" / "workflow_source",
        policy=SideEffectPolicy(mode="dry_run"),
    )
    replay = replay_workflow(
        Path(source["run_dir"]),
        run_root=tmp_path / "runtime" / "runs" / "workflow_replay",
        policy=SideEffectPolicy(
            mode="replay",
            allowed_guarded=frozenset({WRITES_CSV}),
            confirmed_nodes=frozenset({"export_csv"}),
            include_auto_in_replay=True,
        ),
    )

    export_records = replay["nodes"]["export_csv"]["side_effects"]
    assert replay["status"] == "completed_with_blocked"
    assert any(record["kind"] == WRITES_CSV and record["decision"] == "blocked_replay" for record in export_records)
    assert _rename_plan_csvs_under(sample) == []


def test_missing_pdf_and_missing_iso_list_fail_gracefully(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    _patch_sync_iso_worker(monkeypatch)
    _patch_sync_workflow_job(monkeypatch)

    missing_pdf_folder = tmp_path / "missing_pdf"
    missing_pdf_folder.mkdir()
    iso_list = missing_pdf_folder / "iso_list.xlsx"
    _write_iso_list(iso_list)
    missing_pdf = _run_safe_job(
        missing_pdf_folder,
        {"work_folder": str(missing_pdf_folder), "combine_pdf": str(missing_pdf_folder / "missing.pdf"), "iso_list": str(iso_list)},
    )

    missing_iso_folder = _sample_workspace(tmp_path / "missing_iso", pages=1)
    missing_iso = _run_safe_job(
        missing_iso_folder,
        {
            "work_folder": str(missing_iso_folder),
            "combine_pdf": str(missing_iso_folder / "combine.pdf"),
            "iso_list": str(missing_iso_folder / "missing.xlsx"),
            "detect_serials": False,
        },
    )

    assert missing_pdf["result"]["status"] == "failed"
    assert "combine PDF" in _payload_text(missing_pdf)
    assert missing_iso["result"]["status"] == "failed"
    assert "ISO List" in _payload_text(missing_iso)
    assert _rename_plan_csvs_under(missing_pdf_folder) == []
    assert _rename_plan_csvs_under(missing_iso_folder) == []


def test_chinese_and_space_paths_complete_safe_workflow(tmp_path, monkeypatch) -> None:
    sample = _sample_workspace(tmp_path / "測試 資料夾 t", pages=2)
    _redirect_runtime(monkeypatch, tmp_path)
    _patch_sync_iso_worker(monkeypatch)

    result = _run_safe_poc(tmp_path, sample)
    projected = plan_from_run(Path(result["run_dir"]))

    assert result["status"] == "completed"
    assert projected["summary"]["total"] == 2
    assert projected["summary"]["selected"] == 2
    assert _rename_plan_csvs_under(sample) == []


def test_large_pdf_smoke_progress_is_monotonic(tmp_path, monkeypatch) -> None:
    _redirect_runtime(monkeypatch, tmp_path)
    sample = _sample_workspace(tmp_path / "large", pages=60)
    job_dir = tmp_path / "runtime" / "jobs" / "iso" / "large-job"
    job_dir.mkdir(parents=True)
    _write_json(
        job_dir / "request.json",
        {
            "action": "start_batch_detect",
            "combine_pdf": str(sample / "combine.pdf"),
            "iso_list": str(sample / "iso_list.xlsx"),
            "detect_serials": False,
            "job_id": "large-job",
        },
    )
    _write_json(job_dir / "job.json", _job_payload("large-job"))
    progress_done: list[int] = []
    real_write_json = tauri_iso_worker._write_json

    def capture_progress(path: Path, payload: dict[str, object]) -> None:
        if path.name == "job.json":
            progress = payload.get("progress") if isinstance(payload, dict) else {}
            if isinstance(progress, dict):
                progress_done.append(int(progress.get("done") or 0))
        real_write_json(path, payload)

    monkeypatch.setattr(tauri_iso_worker, "_write_json", capture_progress)
    started = time.monotonic()
    job = tauri_iso_worker.run_job(job_dir)
    elapsed = time.monotonic() - started

    assert job["state"] == "completed"
    assert len(job["rows"]) == 60
    assert job["progress"]["done"] == 60
    assert progress_done == sorted(progress_done)
    assert elapsed < 120
    assert _rename_plan_csvs_under(sample) == []


def _sample_workspace(folder: Path, *, pages: int) -> Path:
    folder.mkdir(parents=True)
    _write_pdf(folder / "combine.pdf", pages=pages)
    _write_iso_list(folder / "iso_list.xlsx")
    return folder


def _redirect_runtime(monkeypatch, root: Path) -> None:
    monkeypatch.setenv(PROJECT_ROOT_ENV, str(root / "project_root"))
    monkeypatch.setenv(STATE_PATH_ENV, str(root / "state.json"))
    monkeypatch.setenv("DESKTOP_SUPPORT_JOB_ROOT", str(root / "runtime" / "jobs" / "iso"))
    monkeypatch.setenv("DESKTOP_SUPPORT_ISO_RUN_ROOT", str(root / "runtime" / "runs" / "iso"))
    monkeypatch.setenv("DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT", str(root / "runtime" / "jobs" / "workflow"))
    monkeypatch.setenv("DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT", str(root / "runtime" / "runs" / "workflow"))


def _patch_sync_iso_worker(monkeypatch) -> None:
    monkeypatch.setattr(tauri_iso_workflow, "_spawn_iso_worker", lambda job_dir: tauri_iso_worker.run_job(job_dir))


def _patch_sync_workflow_job(monkeypatch) -> None:
    monkeypatch.setattr(tauri_iso_workflow, "_spawn_workflow_job", lambda job_dir: tauri_workflow_job.run_job(job_dir))


def _run_safe_poc(root: Path, sample: Path) -> dict[str, object]:
    return run_workflow(
        load_workflow(SAFE_WORKFLOW_PATH),
        inputs=_safe_inputs(sample),
        run_root=root / "runtime" / "runs" / "workflow",
    )


def _run_safe_job(sample: Path, inputs: dict[str, object]) -> dict[str, object]:
    defaults = _safe_inputs(sample)
    defaults.update(inputs)
    return tauri_iso_workflow.workflow_run_action(
        IsoWorkflowRequest(
            action="workflow_run",
            workflow_path=SAFE_WORKFLOW_PATH,
            workflow_inputs=defaults,
        )
    )


def _safe_inputs(sample: Path) -> dict[str, object]:
    return {
        "work_folder": str(sample),
        "combine_pdf": str(sample / "combine.pdf"),
        "iso_list": str(sample / "iso_list.xlsx"),
        "sheet_name": "ISO",
        "serial_col": 0,
        "line_col": 1,
        "pattern": "{serial}--{line}.pdf",
        "detect_serials": False,
        "confidence_threshold": 0.7,
        "serial_region": None,
        "drawing_region": None,
    }


def _safe_graph_with_export_enabled():
    payload = json.loads(SAFE_WORKFLOW_PATH.read_text(encoding="utf-8"))
    for node in payload["nodes"]:
        if node["node_id"] == "export_csv":
            node["enabled"] = True
            node["requires_confirm"] = True
    return normalize_graph(payload)


def _apply_graph() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_id": "apply_clean_workdir",
        "display_name": "Apply clean workdir",
        "description": "Guarded apply test graph.",
        "inputs": {"rows": []},
        "nodes": [
            {
                "node_id": "apply",
                "node_type": "iso.apply_rename",
                "inputs": {"rows": "$workflow.inputs.rows"},
                "params": {"dry_run": False, "only_ready": True},
                "requires_confirm": True,
            }
        ],
    }


def _row(source: Path, target: Path) -> dict[str, object]:
    return {
        "id": "row-1",
        "page": 1,
        "source_path": str(source),
        "source_name": source.name,
        "serial": "101",
        "line_no": "PIPE-A",
        "new_name": target.name,
        "target_path": str(target),
        "status": "ready",
        "selected": True,
        "confidence": 1.0,
    }


def _rename_plan_csvs_under(folder: Path) -> list[Path]:
    return sorted(folder.glob("**/iso_rename_plan_*.csv"))


def _csvs_under(folder: Path) -> list[Path]:
    return sorted(folder.glob("**/*.csv"))


def _payload_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
