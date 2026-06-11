from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from launcher.app.tauri_iso_worker import run_job
from launcher.plugins.iso_tools.workflow import nodes as _registered_nodes  # noqa: F401 - registers node classes
from launcher.plugins.iso_tools.workflow.executor import run_workflow, validate_graph
from launcher.plugins.iso_tools.workflow.one_click_guard import validate_one_click_plan
from launcher.plugins.iso_tools.workflow.policy import GUARDED
from launcher.plugins.iso_tools.workflow.projection import plan_from_run
from launcher.plugins.iso_tools.workflow.registry import get_registry
from launcher.plugins.iso_tools.workflow.schema import graph_content_hash, load_workflow


ONE_CLICK_WORKFLOW_PATH = Path("launcher/plugins/iso_tools/workflow/workflows/iso_pdf_one_click.workflow.json")
ONE_CLICK_GRAPH_HASH = "sha256:58eb621dfe9dce1edf9066e61f6427018214dc601a6e3408da0ee7869cc652d7"

PLAN_KEYS = {
    "schema_version",
    "action",
    "created_at",
    "source",
    "summary",
    "steps",
    "rows",
    "issues",
    "pilot_results",
}
SOURCE_KEYS = {
    "kind",
    "work_folder",
    "combine_pdf",
    "page_folder",
    "pdf_count",
    "iso_list",
    "sheet_options",
    "sheet_name",
    "headers",
    "serial_col",
    "line_col",
    "record_count",
    "pattern",
    "detect_serials",
    "confidence_threshold",
    "serial_region",
    "drawing_region",
    "profile",
}
SUMMARY_KEYS = {"total", "ready", "warn", "blocked", "selected"}
ROW_KEYS = {
    "id",
    "page",
    "source_path",
    "source_name",
    "serial",
    "line_no",
    "new_name",
    "target_path",
    "status",
    "selected",
    "confidence",
    "vision_message",
    "note",
}
PILOT_KEYS = {
    "id",
    "stage",
    "status",
    "user_text",
    "engineer_detail",
    "metrics",
    "auto_fix",
    "manual_hint",
    "blocks_apply",
    "issue_codes",
}


def test_one_click_workflow_is_locked_and_hash_pinned() -> None:
    graph = load_workflow(ONE_CLICK_WORKFLOW_PATH)
    issues = validate_graph(graph)
    registry = get_registry()
    guarded_nodes = []
    for node in graph.nodes:
        spec = registry.get_spec(node.node_type)
        if spec.guarded or (set(spec.side_effects) & GUARDED):
            guarded_nodes.append(node.node_id)

    assert issues == []
    assert graph.workflow_id == "iso_pdf_one_click"
    assert graph.metadata.get("locked") is True
    assert [node.node_id for node in graph.nodes] == ["split", "load_table", "batch_detect", "pilot"]
    assert {node.node_type for node in graph.nodes} == {
        "iso.split_pdf",
        "iso.load_iso_table",
        "iso.batch_detect_serials",
        "iso.pilot_report",
    }
    assert guarded_nodes == []
    assert not any(node.node_type in {"iso.export_plan_csv", "iso.apply_rename"} for node in graph.nodes)
    assert graph_content_hash(graph) == ONE_CLICK_GRAPH_HASH


def test_legacy_and_workflow_projection_satisfy_one_click_contract(tmp_path, monkeypatch) -> None:
    sample = _sample_workspace(tmp_path / "sample", pages=2)
    inputs = _workflow_inputs(sample)
    legacy = _legacy_worker_result(tmp_path, inputs, monkeypatch)
    workflow = load_workflow(ONE_CLICK_WORKFLOW_PATH)

    with _patched_runtime(monkeypatch, tmp_path / "workflow_runtime"):
        monkeypatch.setattr("launcher.app.tauri_iso_workflow._spawn_iso_worker", lambda job_dir: run_job(Path(job_dir)))
        result = run_workflow(workflow, inputs=inputs, run_root=tmp_path / "workflow_runs")
    projected = plan_from_run(Path(result["run_dir"]), one_click_guard=True)

    _assert_plan_contract(legacy)
    _assert_plan_contract(projected)
    assert projected["action"] == "workflow_plan_from_run"
    assert projected["summary"] == legacy["summary"]
    assert _row_digest(projected["rows"]) == _row_digest(legacy["rows"])


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda run_log, _plan: run_log.update({"status": "completed_with_blocked"}), "status must be completed"),
        (lambda _run_log, plan: plan.update({"rows": []}), "rows must not be empty"),
        (lambda _run_log, plan: plan["source"].update({"pdf_count": 99}), "rows length must match"),
        (lambda _run_log, plan: _duplicate_selected_target(plan), "target_path duplicated"),
        (lambda _run_log, plan: plan.update({"pilot_results": [{"id": "P02"}]}), "contain P01"),
    ],
)
def test_validate_one_click_plan_rejects_guard_invariants(mutator, message) -> None:
    run_log = {"status": "completed"}
    plan = _base_plan([_row(1), _row(2)])
    mutator(run_log, plan)

    assert any(message in error for error in validate_one_click_plan(run_log, plan))


def test_plan_from_run_one_click_guard_raises_with_specific_errors(tmp_path) -> None:
    run_dir = tmp_path / "wf-blocked"
    _write_projection_run(run_dir, [_row(1)], status="completed_with_blocked")

    with pytest.raises(ValueError, match="status must be completed"):
        plan_from_run(run_dir, one_click_guard=True)


def test_frontend_plan_consumption_stays_inside_contract() -> None:
    text = "\n".join(
        [
            Path("frontend/tauri-spike/src/iso/IsoBoard.tsx").read_text(encoding="utf-8"),
            Path("frontend/tauri-spike/src/iso/AutopilotView.tsx").read_text(encoding="utf-8"),
        ]
    )
    plan_fields = _fields(text, ("plan", "currentPlan"))
    source_fields = _nested_fields(text, ("plan", "currentPlan"), "source")
    summary_fields = _nested_fields(text, ("plan", "currentPlan"), "summary")
    row_fields = _fields(text, ("row",))

    assert plan_fields - {"rows", "source", "summary", "issues", "pilot_results", "pilot_summary"} == set()
    assert source_fields - SOURCE_KEYS == set()
    assert summary_fields - SUMMARY_KEYS == set()
    assert row_fields - ROW_KEYS == set()


def _legacy_worker_result(tmp_path: Path, inputs: dict[str, object], monkeypatch) -> dict[str, object]:
    runtime = tmp_path / "legacy_runtime"
    job_dir = runtime / "jobs" / "iso" / "legacy-contract"
    job_dir.mkdir(parents=True)
    _write_json(job_dir / "request.json", {"action": "start_batch_detect", **inputs, "job_id": "legacy-contract"})
    _write_json(job_dir / "job.json", _job_payload("legacy-contract"))
    with _patched_runtime(monkeypatch, runtime):
        job = run_job(job_dir)
    assert job["state"] == "completed"
    return job["result"]


@contextmanager
def _patched_runtime(monkeypatch, root: Path) -> Iterator[None]:
    with monkeypatch.context() as scoped:
        scoped.setenv("DESKTOP_SUPPORT_JOB_ROOT", str(root / "jobs" / "iso"))
        scoped.setenv("DESKTOP_SUPPORT_ISO_RUN_ROOT", str(root / "runs" / "iso"))
        scoped.setenv("DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT", str(root / "jobs" / "workflow"))
        scoped.setenv("DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT", str(root / "runs" / "workflow"))
        yield


def _sample_workspace(folder: Path, *, pages: int) -> Path:
    folder.mkdir(parents=True)
    _write_pdf(folder / "combine.pdf", pages=pages)
    _write_iso_list(folder / "iso_list.xlsx", rows=pages)
    return folder


def _workflow_inputs(sample: Path) -> dict[str, object]:
    return {
        "work_folder": str(sample),
        "combine_pdf": str(sample / "combine.pdf"),
        "page_folder": "",
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


def _assert_plan_contract(plan: dict[str, object]) -> None:
    assert PLAN_KEYS <= set(plan)
    assert SOURCE_KEYS <= set(plan["source"])
    assert SUMMARY_KEYS <= set(plan["summary"])
    assert isinstance(plan["rows"], list) and plan["rows"]
    assert isinstance(plan["pilot_results"], list) and plan["pilot_results"]
    for row in plan["rows"]:
        assert ROW_KEYS <= set(row)
    for item in plan["pilot_results"]:
        assert PILOT_KEYS <= set(item)


def _row_digest(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keys = ("page", "source_name", "serial", "line_no", "new_name", "status", "selected")
    return [{key: row.get(key) for key in keys} for row in rows]


def _base_plan(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "action": "workflow_plan_from_run",
        "created_at": "test",
        "source": {
            "kind": "page_folder",
            "work_folder": "C:/tmp",
            "combine_pdf": "",
            "page_folder": "C:/tmp/pages",
            "pdf_count": len(rows),
            "iso_list": "C:/tmp/iso.xlsx",
            "sheet_name": "ISO",
            "headers": ["流水號", "圖號"],
            "serial_col": 0,
            "line_col": 1,
            "record_count": len(rows),
            "pattern": "{serial}--{line}.pdf",
            "detect_serials": False,
            "confidence_threshold": 0.7,
            "serial_region": None,
            "drawing_region": None,
            "profile": {},
        },
        "summary": {
            "total": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "ready"),
            "warn": sum(1 for row in rows if row["status"] == "warn"),
            "blocked": sum(1 for row in rows if row["status"] == "blocked"),
            "selected": sum(1 for row in rows if row["selected"]),
        },
        "steps": [],
        "rows": rows,
        "issues": [],
        "pilot_results": [{"id": "P01", "stage": "source", "status": "ready", "user_text": "", "engineer_detail": "", "metrics": {}, "auto_fix": "", "manual_hint": "", "blocks_apply": False, "issue_codes": []}],
    }


def _duplicate_selected_target(plan: dict[str, object]) -> None:
    rows = plan["rows"]
    assert isinstance(rows, list)
    rows[1]["target_path"] = rows[0]["target_path"]


def _write_projection_run(run_dir: Path, rows: list[dict[str, object]], *, status: str = "completed") -> None:
    run_dir.mkdir(parents=True)
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir()
    plan = _base_plan(rows)
    outputs = {
        "batch": {
            "result": _artifact(run_dir, "batch.result", plan),
            "rows": _artifact(run_dir, "batch.rows", rows),
        },
        "pilot": {
            "pilot_results": _artifact(run_dir, "pilot.pilot_results", plan["pilot_results"]),
        },
    }
    run_log = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "mode": "run",
        "workflow_id": "iso_pdf_one_click",
        "graph_hash": ONE_CLICK_GRAPH_HASH,
        "status": status,
        "topology": ["batch", "pilot"],
        "workflow": {
            "nodes": [
                {"node_id": "batch", "node_type": "iso.batch_detect_serials"},
                {"node_id": "pilot", "node_type": "iso.pilot_report"},
            ]
        },
        "nodes": {
            "batch": {"status": "success", "outputs": outputs["batch"], "side_effects": [], "logs": []},
            "pilot": {"status": "success", "outputs": outputs["pilot"], "side_effects": [], "logs": []},
        },
    }
    (run_dir / "run_log.json").write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact(run_dir: Path, name: str, payload: object) -> dict[str, object]:
    path = run_dir / "artifacts" / f"{name}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    data = path.read_bytes()
    return {"artifact_ref": str(path.relative_to(run_dir)).replace("\\", "/"), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _row(page: int, status: str = "ready", selected: bool = True) -> dict[str, object]:
    return {
        "id": f"row-{page}",
        "page": page,
        "source_path": f"C:/tmp/page_{page:03}.pdf",
        "source_name": f"page_{page:03}.pdf",
        "serial": str(page),
        "line_no": f"PIPE-{page:03}",
        "new_name": f"{page}--PIPE-{page:03}.pdf",
        "target_path": f"C:/tmp/{page}--PIPE-{page:03}.pdf",
        "status": status,
        "selected": selected,
        "confidence": 1.0,
        "vision_message": "",
        "note": "",
    }


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


def _fields(text: str, names: tuple[str, ...]) -> set[str]:
    joined = "|".join(re.escape(name) for name in names)
    return set(re.findall(rf"\b(?:{joined})\??\.([A-Za-z_][A-Za-z0-9_]*)", text))


def _nested_fields(text: str, names: tuple[str, ...], nested: str) -> set[str]:
    joined = "|".join(re.escape(name) for name in names)
    return set(re.findall(rf"\b(?:{joined})\??\.{re.escape(nested)}\.([A-Za-z_][A-Za-z0-9_]*)", text))
