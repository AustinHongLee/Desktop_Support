from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EntrypointSmokeTests(unittest.TestCase):
    def test_root_keeps_single_human_entrypoint(self) -> None:
        root_scripts = sorted(
            path.name
            for path in PROJECT_ROOT.iterdir()
            if path.is_file() and path.suffix.lower() in {".cmd", ".bat", ".vbs"}
        )

        self.assertEqual(root_scripts, ["START_HERE.cmd"])

    def test_start_here_menu_matches_choice_codes(self) -> None:
        text = (PROJECT_ROOT / "START_HERE.cmd").read_text(encoding="utf-8")
        labels = re.findall(r"^echo ([1-6])\. (.+)$", text, flags=re.MULTILINE)

        self.assertEqual(
            labels,
            [
                ("1", "Start Desktop Support"),
                ("2", "Debug startup"),
                ("3", "Right-click menu manager"),
                ("4", "Run unit tests"),
                ("5", "Tauri dev/test UI"),
                ("6", "Check dev environment"),
            ],
        )
        self.assertIn("choice /C 123456Q", text)
        self.assertIn('-Suite unit', text)
        self.assertIn('-Suite env', text)

    def test_start_here_quit_path_runs(self) -> None:
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "echo Q| .\\START_HERE.cmd"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Desktop Support", result.stdout)
        self.assertIn("Run unit tests", result.stdout)


class DevEnvironmentSmokeTests(unittest.TestCase):
    def test_dev_env_json_schema(self) -> None:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "scripts" / "dev" / "prepare_dev_environment.ps1"),
                "-Json",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            timeout=45,
            check=False,
        )

        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, stderr)
        payload = json.loads(stdout)
        project_root = str(payload["projectRoot"])
        self.assertTrue(project_root, "projectRoot should not be empty")
        self.assertTrue(
            project_root == str(PROJECT_ROOT)
            or Path(project_root).name == PROJECT_ROOT.name
            or Path(project_root).is_absolute(),
            project_root,
        )
        self.assertIsInstance(payload["nativeTauriReady"], bool)
        self.assertIsInstance(payload["checks"], list)
        self.assertGreaterEqual(len(payload["checks"]), 5)
        for check in payload["checks"]:
            self.assertIn("name", check)
            self.assertIn("ok", check)
            self.assertIn("detail", check)
            self.assertIn("fix", check)


class ImportSmokeTests(unittest.TestCase):
    def test_dock_window_shutdown_message_helper_imports(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from launcher.ui import dock_window

        self.assertTrue(callable(dock_window._windows_message_id))
        self.assertEqual(dock_window._windows_message_id(0), 0)

    def test_tauri_browser_fallback_entry_is_present(self) -> None:
        text = (PROJECT_ROOT / "scripts" / "tauri" / "run_dev_app.ps1").read_text(encoding="utf-8")

        self.assertIn("Start-BrowserFallback", text)
        self.assertIn("http://127.0.0.1:1420/?surface=dock", text)

    def test_vite_dev_server_ignores_tauri_build_outputs(self) -> None:
        text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "vite.config.ts").read_text(encoding="utf-8")

        self.assertIn("watch", text)
        self.assertIn("**/src-tauri/target/**", text)
        self.assertIn("**/src-tauri/backend-build/**", text)
        self.assertIn("**/src-tauri/backend-dist/**", text)

    def test_tauri_tray_quit_uses_shutdown_safety_gate(self) -> None:
        text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")

        self.assertIn("TRAY_QUIT => request_shutdown_safe_quit(app)", text)
        self.assertIn("fn request_shutdown_safe_quit", text)
        self.assertNotIn("TRAY_QUIT => app.exit(0)", text)

    def test_tauri_close_hide_has_first_run_notice(self) -> None:
        text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")

        self.assertIn("maybe_show_hide_to_tray_notice();", text)
        self.assertIn("HIDE_TO_TRAY_NOTICE_FLAG", text)
        self.assertIn("MessageDialog::new()", text)

    def test_iso_one_click_failure_card_is_handoff_only(self) -> None:
        app_text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src" / "App.tsx").read_text(encoding="utf-8")
        card_text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src" / "iso" / "components" / "FailureCard.tsx").read_text(encoding="utf-8")
        workflow_text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src" / "isoWorkflow.ts").read_text(encoding="utf-8")

        self.assertIn("FailureCard", app_text)
        self.assertIn("exportIsoDebugBundle", app_text)
        self.assertIn('run_id?: string', workflow_text)
        self.assertIn('"export_debug_bundle"', workflow_text)
        self.assertIn("複製給工程師", card_text)
        self.assertIn("匯出問題包", card_text)
        self.assertIn("開啟工作台", card_text)
        self.assertNotIn("ROI", card_text)
        self.assertNotIn("threshold", card_text.casefold())
        self.assertNotIn("legacy", card_text.casefold())

    def test_iso_autopilot_keeps_legacy_bridge_outside_one_click(self) -> None:
        text = (PROJECT_ROOT / "frontend" / "tauri-spike" / "src" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn('{isoView !== "autopilot" ? (', text)
        self.assertIn('title="暫時開啟舊版工作台(轉移完成後移除)"', text)
        self.assertNotIn('isoView === "autopilot" ? (\n            <button className="icon-button" onClick={legacy.launch}', text)


if __name__ == "__main__":
    unittest.main()
