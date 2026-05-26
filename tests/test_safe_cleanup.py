from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.core.context_model import LauncherContext
from launcher.core.safe_cleanup import (
    BLOCKED_LAYER,
    PROCESS_LAYER,
    REVIEW_LAYER,
    SAFE_LAYER,
    CleanupPlanItem,
    apply_cleanup_plan,
    build_cleanup_plan,
)


class SafeCleanupTests(unittest.TestCase):
    def test_plan_layers_target_and_associated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "ABC.pdf"
            sibling = root / "ABC_page_001.pdf"
            target.write_text("pdf", encoding="utf-8")
            sibling.write_text("page", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        layers = {item.label: item.layer for item in plan.items}
        self.assertEqual(layers["ABC.pdf"], SAFE_LAYER)
        self.assertEqual(layers["ABC_page_001.pdf"], REVIEW_LAYER)

    def test_context_folder_is_review_not_default_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext(folder=root, source="test"), state_path=root / "state.json")

        self.assertEqual(plan.items[0].layer, REVIEW_LAYER)
        self.assertFalse(plan.items[0].checked_default)

    def test_exe_under_localappdata_programs_suggests_install_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_root = root / "Programs" / "cursor"
            app_root.mkdir(parents=True)
            target = app_root / "Cursor.exe"
            target.write_text("x", encoding="utf-8")

            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        install_item = next(item for item in plan.items if item.kind == "install_folder")
        self.assertEqual(install_item.layer, REVIEW_LAYER)
        self.assertEqual(Path(install_item.path), app_root)

    def test_plan_includes_running_process_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.exe"
            target.write_text("x", encoding="utf-8")
            process_item = CleanupPlanItem(
                id="process:123",
                layer=PROCESS_LAYER,
                kind="running_process",
                label="app.exe (PID 123)",
                action="嘗試關閉程序",
                note="程序執行檔就是目前目標。",
                checked_default=False,
                process_id=123,
                process_name="app.exe",
                process_path=str(target),
                can_close=True,
            )

            with patch("launcher.core.safe_cleanup._running_process_items", return_value=[process_item]):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        item = next(entry for entry in plan.items if entry.kind == "running_process")
        self.assertEqual(item.layer, PROCESS_LAYER)
        self.assertTrue(item.executable)

    def test_apply_can_close_selected_process_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.exe"
            target.write_text("x", encoding="utf-8")
            process_item = CleanupPlanItem(
                id="process:123",
                layer=PROCESS_LAYER,
                kind="running_process",
                label="app.exe (PID 123)",
                action="嘗試關閉程序",
                note="程序執行檔就是目前目標。",
                checked_default=False,
                process_id=123,
                process_name="app.exe",
                process_path=str(target),
                can_close=True,
            )

            with patch("launcher.core.safe_cleanup._running_process_items", return_value=[process_item]):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            with patch("launcher.core.safe_cleanup._close_process") as close_process:
                result = apply_cleanup_plan(
                    plan,
                    {process_item.id},
                    include_process_close=True,
                    quarantine_root=root / "quarantine",
                )

        close_process.assert_called_once_with(123)
        self.assertEqual(result.closed_process_count, 1)

    def test_missing_target_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.txt"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([missing]), state_path=Path(tmp) / "state.json")

        self.assertEqual(plan.items[0].layer, BLOCKED_LAYER)
        self.assertFalse(plan.items[0].executable)

    def test_apply_moves_file_to_quarantine_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "delete_me.txt"
            target.write_text("x", encoding="utf-8")
            quarantine = root / "quarantine"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=quarantine)

            self.assertFalse(target.exists())
            self.assertEqual(result.moved_count, 1)
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["moved"][0]["item"]["label"], "delete_me.txt")

    def test_state_record_cleanup_removes_matching_recent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("x", encoding="utf-8")
            state = root / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "recent_files": [str(target), str(root / "keep.txt")],
                        "recent_folders": [str(root)],
                        "recent_contexts": [{"folder": str(root), "files": [str(target)], "source": "test"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=state)
            state_item = next(item for item in plan.items if item.kind == "state_record")
            apply_cleanup_plan(plan, {state_item.id}, quarantine_root=root / "quarantine")

            data = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(data["recent_files"], [str(root / "keep.txt")])
            self.assertEqual(data["recent_contexts"], [])


if __name__ == "__main__":
    unittest.main()
