from __future__ import annotations

import unittest
from pathlib import Path

from launcher.windows.context_menu_registry import (
    CONTEXT_MENU_TARGETS,
    ContextMenuEntry,
    ContextMenuLocation,
    ContextMenuTargetStatus,
    ExplorerContextMenuStatus,
    entry_detail_lines,
    expected_context_menu_command,
    status_lines,
)


class ContextMenuRegistryTests(unittest.TestCase):
    def test_expected_command_wakes_existing_instance_and_passes_context(self) -> None:
        command = expected_context_menu_command(Path("C:/Tool/.venv/Scripts/pythonw.exe"), "%1")

        self.assertIn("--show-existing", command)
        self.assertIn("--context-source explorer.menu", command)
        self.assertIn('--set-context "%1"', command)

    def test_targets_cover_common_explorer_contexts(self) -> None:
        labels = {target.label for target in CONTEXT_MENU_TARGETS}

        self.assertEqual(labels, {"檔案", "資料夾", "資料夾空白處", "磁碟機"})

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


if __name__ == "__main__":
    unittest.main()
