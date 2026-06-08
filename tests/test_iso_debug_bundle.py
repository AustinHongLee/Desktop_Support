from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from launcher.plugins.iso_tools.debug_bundle import export_iso_debug_bundle
from launcher.plugins.iso_tools.run_log import finish_iso_run_failure, start_iso_run


class IsoDebugBundleTests(unittest.TestCase):
    def test_export_debug_bundle_contains_diagnostics_but_not_original_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "runs"
            pdf = root / "combine.pdf"
            iso_list = root / "iso_list.xlsx"
            pdf.write_bytes(b"%PDF-placeholder")
            iso_list.write_text("placeholder", encoding="utf-8")

            with patch.dict(os.environ, {"DESKTOP_SUPPORT_ISO_RUN_ROOT": str(run_root)}):
                context = start_iso_run(
                    {
                        "action": "plan",
                        "combine_pdf": str(pdf),
                        "iso_list": str(iso_list),
                    },
                    action="plan",
                    run_id="iso-debug-test",
                )
                try:
                    raise ValueError("ISO List 沒有有效資料。")
                except ValueError as exc:
                    finish_iso_run_failure(context, exc)
                run_json = run_root / "iso-debug-test" / "run.json"
                run_payload = json.loads(run_json.read_text(encoding="utf-8"))
                run_payload["rows"] = [
                    {
                        "selected": True,
                        "page": 1,
                        "source_name": "p001.pdf",
                        "serial": "1",
                        "line_no": "PIPE-A",
                        "new_name": "1--PIPE-A.pdf",
                        "status": "ready",
                    }
                ]
                run_json.write_text(json.dumps(run_payload, ensure_ascii=False), encoding="utf-8")
                result = export_iso_debug_bundle("iso-debug-test")

            bundle = Path(result["export_path"])
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
                run_payload = json.loads(archive.read("run.json").decode("utf-8"))
                env_payload = json.loads(archive.read("env.json").decode("utf-8"))
                plan_csv = archive.read("plan.csv").decode("utf-8")

        self.assertIn("run.json", names)
        self.assertIn("events.jsonl", names)
        self.assertIn("plan.csv", names)
        self.assertIn("pilot.json", names)
        self.assertIn("profile.json", names)
        self.assertIn("env.json", names)
        self.assertIn("README.txt", names)
        self.assertNotIn("combine.pdf", names)
        self.assertNotIn("iso_list.xlsx", names)
        self.assertFalse(env_payload["contains_original_pdf_or_xlsx"])
        self.assertEqual(run_payload["failure"]["failed_stage"], "iso_parse")
        self.assertIn("1--PIPE-A.pdf", plan_csv)


if __name__ == "__main__":
    unittest.main()
