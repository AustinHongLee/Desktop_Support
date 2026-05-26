from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.safe_cleanup import CleanupPlan, CleanupPlanItem, REGISTRY_LAYER, apply_cleanup_plan, build_cleanup_plan  # noqa: E402
from launcher.ui.quarantine_browser_dialog import QuarantineBrowserDialog  # noqa: E402


class QuarantineBrowserDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_lists_quarantine_sessions_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "old.log"
            target.write_text("log", encoding="utf-8")
            quarantine = root / "quarantine"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=quarantine)

            dialog = QuarantineBrowserDialog(quarantine_root=quarantine)

        self.assertEqual(dialog.windowTitle(), "隔離區管理")
        self.assertEqual(dialog._session_table.rowCount(), 1)
        self.assertEqual(dialog._record_table.rowCount(), 1)
        self.assertIn("old.log", dialog._record_table.item(0, 1).text())
        self.assertEqual(dialog._sessions[0].path, result.quarantine_dir)
        self.assertEqual(dialog._session_table.item(0, 3).text(), "0")

    def test_dialog_lists_registry_cleanup_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quarantine = root / "quarantine"
            registry_item = CleanupPlanItem(
                id="registry:HKCU:Software\\Demo:InstallPath",
                layer=REGISTRY_LAYER,
                kind="registry_value",
                label="HKCU\\Demo\\InstallPath",
                action="刪除登錄值",
                note="測試",
                checked_default=False,
                root_name="HKCU",
                registry_key="Software\\Demo",
                registry_value_name="InstallPath",
                registry_value_data="C:\\Demo",
            )
            plan = CleanupPlan(targets=(), items=(registry_item,), created_at=0)

            def fake_export(_item: CleanupPlanItem, session_dir: Path, _index: int) -> Path:
                export_path = session_dir / "registry-001-demo.reg"
                export_path.write_text("Windows Registry Editor Version 5.00", encoding="utf-8")
                return export_path

            with patch("launcher.core.safe_cleanup._export_registry_key", side_effect=fake_export):
                with patch("launcher.core.safe_cleanup._delete_registry_value"):
                    result = apply_cleanup_plan(
                        plan,
                        {registry_item.id},
                        include_registry=True,
                        quarantine_root=quarantine,
                    )

            dialog = QuarantineBrowserDialog(quarantine_root=quarantine)

        self.assertEqual(dialog._sessions[0].path, result.quarantine_dir)
        self.assertEqual(dialog._session_table.item(0, 3).text(), "1")
        self.assertEqual(dialog._registry_table.rowCount(), 1)
        self.assertIn("Software\\Demo", dialog._registry_table.item(0, 1).text())
        self.assertIn("registry-001-demo.reg", dialog._registry_table.item(0, 2).text())


if __name__ == "__main__":
    unittest.main()
