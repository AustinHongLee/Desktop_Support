from __future__ import annotations

import unittest
from pathlib import Path

from launcher.windows.context_menu_registry import (
    CONTEXT_MENU_TARGETS,
    CUSTOM_CONTEXT_MENU_TARGETS,
    CUSTOM_VERB_PREFIX,
    ContextMenuEntry,
    ContextMenuLocation,
    ContextMenuTargetStatus,
    ExplorerContextMenuStatus,
    entry_detail_lines,
    expected_context_menu_command,
    expected_iso_workbench_command,
    expected_safe_cleanup_command,
    is_launcher_managed_entry,
    open_with_program_command,
    power_shell_here_command,
    run_script_command,
    status_lines,
)


class ContextMenuRegistryTests(unittest.TestCase):
    def test_expected_command_wakes_existing_instance_and_passes_context(self) -> None:
        command = expected_context_menu_command(Path("C:/Tool/.venv/Scripts/pythonw.exe"), "%1")

        self.assertIn("--show-existing", command)
        self.assertIn("--context-source explorer.menu", command)
        self.assertIn('--set-context "%1"', command)

    def test_expected_iso_command_opens_workbench_with_context(self) -> None:
        command = expected_iso_workbench_command(Path("C:/Tool/.venv/Scripts/pythonw.exe"), "%V")

        self.assertIn("--open-iso-workbench", command)
        self.assertIn('--set-context "%V"', command)

    def test_expected_safe_cleanup_command_opens_workbench_with_context(self) -> None:
        command = expected_safe_cleanup_command(Path("C:/Tool/.venv/Scripts/pythonw.exe"), "%1")

        self.assertIn("--open-safe-cleanup", command)
        self.assertIn('--set-context "%1"', command)

    def test_targets_cover_common_explorer_contexts(self) -> None:
        labels = {target.label for target in CONTEXT_MENU_TARGETS}

        self.assertEqual(labels, {"檔案", "資料夾", "資料夾空白處", "磁碟機"})

    def test_custom_targets_include_desktop_background(self) -> None:
        labels = {target.label for target in CUSTOM_CONTEXT_MENU_TARGETS}

        self.assertIn("桌面空白處", labels)
        self.assertIn("資料夾空白處", labels)

    def test_template_command_builders_quote_target_argument(self) -> None:
        target = CUSTOM_CONTEXT_MENU_TARGETS[0]

        self.assertIn("Split-Path", power_shell_here_command(target))
        self.assertEqual(open_with_program_command("C:/Tools/app.exe", "%1"), '"C:/Tools/app.exe" "%1"')
        self.assertIn("-ExecutionPolicy Bypass", run_script_command("C:/Tools/do.ps1", "%V"))

    def test_status_summary_detects_installed_and_update_states(self) -> None:
        target = CONTEXT_MENU_TARGETS[0]
        expected = "expected"

        installed = ExplorerContextMenuStatus(
            pythonw=Path("pythonw.exe"),
            pythonw_exists=True,
            targets=(ContextMenuTargetStatus(target, True, expected, expected, True),),
        )
        needs_update = ExplorerContextMenuStatus(
            pythonw=Path("pythonw.exe"),
            pythonw_exists=True,
            targets=(ContextMenuTargetStatus(target, True, "old", expected, False),),
        )

        self.assertEqual(installed.summary, "已安裝，設定正確")
        self.assertEqual(needs_update.summary, "已安裝，但需要更新")
        self.assertTrue(needs_update.needs_update)

    def test_status_lines_are_human_readable(self) -> None:
        target = CONTEXT_MENU_TARGETS[0]
        status = ExplorerContextMenuStatus(
            pythonw=Path("C:/Tool/.venv/Scripts/pythonw.exe"),
            pythonw_exists=False,
            targets=(ContextMenuTargetStatus(target, False, expected_command="expected"),),
        )

        lines = status_lines(status)

        self.assertIn("狀態：尚未安裝", lines)
        self.assertIn("Pythonw 存在：否", lines)
        self.assertIn("檔案：未安裝", lines)

    def test_entry_detail_lines_include_registry_identity(self) -> None:
        entry = ContextMenuEntry(
            id="HKCU|shell|Software\\Classes\\Directory\\Background\\shell\\Git Bash",
            label="Git Bash Here",
            key_name="Git Bash",
            root_name="HKCU",
            root_handle=object(),
            location=ContextMenuLocation("資料夾空白處", "Software\\Classes\\Directory\\Background\\shell", "shell"),
            key_path="Software\\Classes\\Directory\\Background\\shell\\Git Bash",
            kind="shell",
            enabled=True,
            editable=True,
            command="git-bash.exe",
        )

        lines = entry_detail_lines(entry)

        self.assertIn("名稱：Git Bash Here", lines)
        self.assertIn("來源：HKCU", lines)
        self.assertIn("Command / CLSID：git-bash.exe", lines)

    def test_launcher_managed_entry_is_detected_by_key_name(self) -> None:
        entry = ContextMenuEntry(
            id="HKCU|shell|x",
            label="自建",
            key_name=f"{CUSTOM_VERB_PREFIX}_Action",
            root_name="HKCU",
            root_handle=object(),
            location=ContextMenuLocation("資料夾空白處", "Software\\Classes\\Directory\\Background\\shell", "shell"),
            key_path="Software\\Classes\\Directory\\Background\\shell\\EngineeringLauncherCustom_Action",
            kind="shell",
            enabled=True,
            editable=True,
        )

        self.assertTrue(is_launcher_managed_entry(entry))


if __name__ == "__main__":
    unittest.main()
