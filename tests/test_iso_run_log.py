from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook
from pypdf import PdfWriter

from launcher.app.tauri_iso_worker import run_job


class IsoRunLogTests(unittest.TestCase):
    def test_cli_failure_writes_replayable_run_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            pdf = root / "combine.pdf"
            iso_list = root / "empty_iso.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list, include_rows=False)

            result = _run_workflow_cli(
                {
                    "action": "plan",
                    "combine_pdf": str(pdf),
                    "iso_list": str(iso_list),
                },
                run_root=run_root,
            )

            run = _single_run(run_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["failure"]["failed_stage"], "iso_parse")
        self.assertIn("ISO List", run["failure"]["user_summary"])
        self.assertEqual(run["replay"]["request"]["action"], "plan")
        self.assertEqual(run["replay"]["request"]["iso_list"], str(iso_list))
        self.assertIn("ISO List 沒有有效資料", run["failure"]["exception_stack"])

    def test_cli_success_writes_completed_run_log_and_returns_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            pdf = root / "combine.pdf"
            iso_list = root / "iso_list.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)

            result = _run_workflow_cli(
                {
                    "action": "plan",
                    "combine_pdf": str(pdf),
                    "iso_list": str(iso_list),
                },
                run_root=run_root,
            )
            payload = json.loads(result.stdout.decode("utf-8"))
            run = json.loads(Path(payload["run_log"]["run_json"]).read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["summary"]["ready"], 1)
        self.assertEqual(run["rows"][0]["new_name"], "1--PIPE-A.pdf")
        self.assertEqual(run["inputs"]["iso_list"], str(iso_list))
        self.assertEqual(payload["run_log"]["run_id"], run["run_id"])

    def test_worker_appends_events_jsonl_and_completes_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            pdf = root / "combine.pdf"
            iso_list = root / "iso_list.xlsx"
            job_dir = root / "jobs" / "job-1"
            job_dir.mkdir(parents=True)
            _write_pdf(pdf, pages=2)
            _write_iso_list(iso_list)
            _write_json(
                job_dir / "request.json",
                {
                    "action": "start_batch_detect",
                    "combine_pdf": str(pdf),
                    "iso_list": str(iso_list),
                    "run_id": "iso-test-worker",
                },
            )
            _write_json(job_dir / "job.json", _job_payload("job-1"))

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_ISO_RUN_ROOT": str(run_root)}):
                job = run_job(job_dir)

            run_path = run_root / "iso-test-worker" / "run.json"
            events_path = run_root / "iso-test-worker" / "events.jsonl"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(job["state"], "completed")
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["summary"]["ready"], 2)
        self.assertEqual(run["rows"][1]["new_name"], "2--PIPE-B.pdf")
        self.assertTrue(any(event["code"] == "ROW_DONE" for event in events))


def _run_workflow_cli(payload: dict[str, object], *, run_root: Path) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "DESKTOP_SUPPORT_ISO_RUN_ROOT": str(run_root)}
    return subprocess.run(
        [sys.executable, "-m", "launcher.app.tauri_iso_workflow"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )


def _single_run(run_root: Path) -> dict[str, object]:
    runs = sorted(path for path in run_root.iterdir() if path.is_dir())
    if len(runs) != 1:
        raise AssertionError(f"expected one run log, got {runs}")
    return json.loads((runs[0] / "run.json").read_text(encoding="utf-8"))


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_iso_list(path: Path, *, include_rows: bool = True) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    if include_rows:
        sheet.append(["1", "PIPE-A"])
        sheet.append(["2", "PIPE-B"])
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
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
