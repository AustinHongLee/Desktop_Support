from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.app.tauri_iso_worker import run_job
from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, build_iso_plan
from launcher.plugins.iso_tools.workflow import nodes as _registered_nodes  # noqa: F401 - registers node classes
from launcher.plugins.iso_tools.workflow.executor import run_workflow
from launcher.plugins.iso_tools.workflow.schema import load_workflow
from launcher.plugins.iso_tools.workflow.projection import plan_from_run, read_artifact
from tests.test_tauri_iso_workflow import _write_iso_list, _write_pdf


class IsoWorkflowProjectionTests(unittest.TestCase):
    def test_plan_from_run_prefers_batch_result_and_fresh_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "wf-1"
            rows = [_row(1, "ready", True), _row(2, "warn", False)]
            base_plan = {
                "schema_version": 1,
                "action": "batch_detect_result",
                "source": {"work_folder": str(run_dir.parent), "pdf_count": 2},
                "summary": {"total": 99, "ready": 99, "warn": 0, "blocked": 0, "selected": 99},
                "rows": rows,
                "issues": [],
                "pilot_results": [{"id": "OLD", "status": "warn"}],
            }
            fresh_pilot = [{"id": "P01", "status": "ready", "blocks_apply": False}]
            outputs = {
                "batch": {
                    "result": base_plan,
                    "rows": rows,
                    "iso_run_log": {"run_id": "iso-1", "run_dir": "C:/runs/iso-1"},
                },
                "pilot": {
                    "pilot_results": fresh_pilot,
                    "pilot_summary": {"ready": 1},
                },
            }
            _write_run(run_dir, outputs)

            projected = plan_from_run(run_dir)

        self.assertEqual(projected["action"], "workflow_plan_from_run")
        self.assertEqual(projected["summary"], {"total": 2, "ready": 1, "warn": 1, "blocked": 0, "selected": 1})
        self.assertEqual(projected["pilot_results"], fresh_pilot)
        self.assertEqual(projected["provenance"]["workflow_run_id"], "wf-1")
        self.assertEqual(projected["provenance"]["rows_node"], "batch")
        self.assertEqual(projected["provenance"]["pilot_node"], "pilot")
        self.assertEqual(projected["provenance"]["iso_run_log"]["run_id"], "iso-1")

    def test_plan_from_run_falls_back_to_build_plan_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "wf-build"
            rows = [_row(1, "ready", True)]
            outputs = {
                "build": {
                    "plan": {
                        "schema_version": 1,
                        "action": "build_rename_plan",
                        "source": {"pdf_count": 1},
                        "summary": {},
                        "rows": rows,
                        "issues": [],
                    }
                }
            }
            _write_run(run_dir, outputs, workflow_nodes=[{"node_id": "build", "node_type": "iso.build_plan"}])

            projected = plan_from_run(run_dir)

        self.assertEqual(projected["summary"]["total"], 1)
        self.assertEqual(projected["provenance"]["rows_node"], "build")

    def test_read_artifact_rejects_unknown_port_and_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "wf-safe"
            outputs = {"batch": {"rows": [_row(1, "ready", True)]}}
            _write_run(run_dir, outputs)
            bad_log = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
            bad_log["nodes"]["batch"]["outputs"]["escape"] = {"artifact_ref": "../escape.json", "bytes": 2, "sha256": "x"}
            (run_dir / "run_log.json").write_text(json.dumps(bad_log), encoding="utf-8")

            _, payload = read_artifact(run_dir, "batch", "rows")

            with self.assertRaisesRegex(ValueError, "not found"):
                read_artifact(run_dir, "batch", "missing")
            with self.assertRaisesRegex(ValueError, "escapes"):
                read_artifact(run_dir, "batch", "escape")
        self.assertEqual(payload[0]["page"], 1)

    def test_read_artifact_rejects_large_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "wf-large"
            outputs = {"batch": {"rows": [_row(1, "ready", True)]}}
            _write_run(run_dir, outputs)
            run_log = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
            run_log["nodes"]["batch"]["outputs"]["rows"]["bytes"] = 64 * 1024 * 1024 + 1
            (run_dir / "run_log.json").write_text(json.dumps(run_log), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "64MB"):
                read_artifact(run_dir, "batch", "rows")

    def test_safe_poc_projection_matches_legacy_plan_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "sample"
            sample.mkdir()
            pdf = sample / "combine.pdf"
            iso_list = sample / "iso_list.xlsx"
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)
            workflow = load_workflow(Path("launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json"))
            inputs = {
                "work_folder": str(sample),
                "combine_pdf": str(pdf),
                "iso_list": str(iso_list),
                "sheet_name": "ISO",
                "serial_col": 0,
                "line_col": 1,
                "pattern": "{serial}--{line}.pdf",
                "detect_serials": False,
                "confidence_threshold": 0.7,
                "serial_region": None,
                "drawing_region": None,
            }

            with patch.dict(
                os.environ,
                {
                    "DESKTOP_SUPPORT_JOB_ROOT": str(root / "iso_jobs"),
                    "DESKTOP_SUPPORT_ISO_RUN_ROOT": str(root / "iso_runs"),
                },
            ), patch("launcher.app.tauri_iso_workflow._spawn_iso_worker", lambda job_dir: run_job(job_dir)):
                result = run_workflow(workflow, inputs=inputs, run_root=root / "workflow_runs")
            projected = plan_from_run(Path(result["run_dir"]))
            legacy = build_iso_plan(
                IsoWorkflowRequest(
                    action="plan",
                    page_folder=Path(projected["source"]["page_folder"]),
                    iso_list=iso_list,
                    sheet_name="ISO",
                    serial_col=0,
                    line_col=1,
                    detect_serials=False,
                )
            )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(_row_digest(projected["rows"]), _row_digest(legacy["rows"]))


def _write_run(
    run_dir: Path,
    outputs: dict[str, dict[str, object]],
    *,
    workflow_nodes: list[dict[str, str]] | None = None,
) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "artifacts").mkdir()
    workflow_nodes = workflow_nodes or [
        {"node_id": "batch", "node_type": "iso.batch_detect_serials"},
        {"node_id": "pilot", "node_type": "iso.pilot_report"},
    ]
    nodes: dict[str, dict[str, object]] = {}
    for node in workflow_nodes:
        node_id = node["node_id"]
        port_payloads = outputs.get(node_id, {})
        nodes[node_id] = {
            "status": "success",
            "outputs": {
                port: _write_artifact(run_dir, node_id, port, payload)
                for port, payload in port_payloads.items()
            },
            "side_effects": [],
            "logs": [],
        }
    run_log = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "mode": "run",
        "workflow_id": "projection_test",
        "run_dir": str(run_dir),
        "graph_hash": "sha256:test",
        "status": "completed",
        "topology": [node["node_id"] for node in workflow_nodes],
        "inputs": {},
        "workflow": {"nodes": workflow_nodes},
        "nodes": nodes,
        "side_effect_summary": {"executed": [], "blocked": [], "skipped": [], "simulated": []},
        "issues": [],
    }
    (run_dir / "run_log.json").write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_artifact(run_dir: Path, node_id: str, port: str, payload: object) -> dict[str, object]:
    path = run_dir / "artifacts" / f"{node_id}.{port}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    data = path.read_bytes()
    return {
        "artifact_ref": str(path.relative_to(run_dir)).replace("\\", "/"),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _row(page: int, status: str, selected: bool) -> dict[str, object]:
    return {
        "id": f"row-{page}",
        "page": page,
        "source_path": f"C:/tmp/page_{page:03d}.pdf",
        "source_name": f"page_{page:03d}.pdf",
        "serial": str(page),
        "line_no": f"PIPE-{page}",
        "new_name": f"{page}--PIPE-{page}.pdf",
        "target_path": f"C:/tmp/{page}--PIPE-{page}.pdf",
        "status": status,
        "selected": selected,
        "confidence": 1.0,
        "vision_message": "",
        "note": "",
    }


def _row_digest(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keys = ("page", "source_name", "serial", "line_no", "new_name", "status", "selected")
    return [{key: row.get(key) for key in keys} for row in rows]
