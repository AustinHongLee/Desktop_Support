from __future__ import annotations

import json
import os
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch

from launcher.core import safe_cleanup as safe_cleanup_module
from launcher.core.context_model import LauncherContext
from launcher.core.safe_cleanup import (
    BLOCKED_LAYER,
    PROCESS_LAYER,
    REGISTRY_LAYER,
    REVIEW_LAYER,
    RestoreConflictPolicy,
    SAFE_LAYER,
    CleanupPlan,
    CleanupPlanItem,
    OfficialUninstaller,
    ScanCancelToken,
    ScanCancelled,
    apply_cleanup_plan,
    build_cleanup_plan,
    delete_quarantine_session,
    list_quarantine_sessions,
    run_official_uninstaller,
    restore_quarantine_items,
    restore_registry_items,
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

    def test_exe_under_program_files_suggests_product_root_as_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            program_files = root / "Program Files"
            app_root = program_files / "Tekla Structures"
            target = app_root / "2026.0" / "bin" / "TeklaStructures.exe"
            target.parent.mkdir(parents=True)
            target.write_text("x", encoding="utf-8")

            with patch.dict(os.environ, {"ProgramFiles": str(program_files)}):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        install_item = next(item for item in plan.items if item.kind == "install_folder")
        self.assertEqual(install_item.layer, BLOCKED_LAYER)
        self.assertEqual(Path(install_item.path), app_root)

    def test_plan_includes_official_uninstaller_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "Programs" / "demo" / "Demo.exe"
            target.parent.mkdir(parents=True)
            target.write_text("x", encoding="utf-8")
            uninstaller = OfficialUninstaller(
                id="uninstaller:HKCU:Demo",
                root_name="HKCU",
                registry_key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Demo",
                display_name="Demo App",
                uninstall_command='"C:\\Demo\\uninstall.exe"',
                match_reason="DisplayIcon 指向目標路徑",
                confidence=0.9,
            )

            with patch("launcher.core.safe_cleanup._official_uninstallers", return_value=[uninstaller]):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        self.assertEqual(plan.official_uninstallers, (uninstaller,))

    def test_plan_includes_app_footprints_from_common_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "LocalAppData"
            roaming = root / "RoamingAppData"
            program_data = root / "ProgramData"
            user_profile = root / "User"
            target = local / "Programs" / "Tekla Structures 2026" / "bin" / "TeklaStructures.exe"
            roaming_footprint = roaming / "Trimble" / "Tekla Structures 2026"
            program_data_footprint = program_data / "Trimble" / "Tekla Structures 2026"
            target.parent.mkdir(parents=True)
            roaming_footprint.mkdir(parents=True)
            program_data_footprint.mkdir(parents=True)
            (roaming_footprint / "settings.json").write_text("{}", encoding="utf-8")
            (program_data_footprint / "template.dat").write_text("x", encoding="utf-8")
            target.write_text("x", encoding="utf-8")
            uninstaller = OfficialUninstaller(
                id="uninstaller:HKLM:Tekla",
                root_name="HKLM",
                registry_key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Tekla Structures 2026",
                display_name="Tekla Structures 2026",
                uninstall_command='"C:\\Program Files\\Tekla\\uninstall.exe"',
                install_location=str(target.parents[1]),
                match_reason="InstallLocation 指向疑似安裝資料夾",
                confidence=0.95,
            )

            with patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(local),
                    "APPDATA": str(roaming),
                    "ProgramData": str(program_data),
                    "USERPROFILE": str(user_profile),
                },
            ):
                with patch("launcher.core.safe_cleanup._official_uninstallers", return_value=[uninstaller]):
                    with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                        plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        footprints = {Path(item.path): item for item in plan.items if item.kind == "app_footprint_folder"}
        self.assertIn(roaming_footprint, footprints)
        self.assertIn(program_data_footprint, footprints)
        self.assertEqual(footprints[roaming_footprint].layer, REVIEW_LAYER)
        self.assertEqual(footprints[program_data_footprint].layer, BLOCKED_LAYER)
        self.assertFalse(footprints[roaming_footprint].checked_default)

    def test_app_footprints_ignore_generic_program_files_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "LocalAppData"
            roaming = root / "RoamingAppData"
            program_data = root / "ProgramData"
            user_profile = root / "User"
            false_positive = local / "Temporary Internet Files"
            true_positive = roaming / "Trimble" / "Tekla Structures 2026"
            false_positive.mkdir(parents=True)
            true_positive.mkdir(parents=True)
            target = Path("C:/Program Files/Tekla Structures/2026.0/bin/TeklaStructures.exe")
            uninstaller = OfficialUninstaller(
                id="uninstaller:HKLM:Tekla",
                root_name="HKLM",
                registry_key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Tekla Structures 2026",
                display_name="Tekla Structures 2026",
                uninstall_command='"C:\\Program Files\\Tekla\\uninstall.exe"',
                install_location="C:\\Program Files\\Tekla Structures\\2026.0",
                confidence=0.95,
            )

            with patch.dict(
                os.environ,
                {
                    "LOCALAPPDATA": str(local),
                    "APPDATA": str(roaming),
                    "ProgramData": str(program_data),
                    "USERPROFILE": str(user_profile),
                },
            ):
                with patch("launcher.core.safe_cleanup._official_uninstallers", return_value=[uninstaller]):
                    with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                        plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")

        footprints = {Path(item.path) for item in plan.items if item.kind == "app_footprint_folder"}
        self.assertIn(true_positive, footprints)
        self.assertNotIn(false_positive, footprints)

    def test_installer_registry_residue_matches_value_names(self) -> None:
        target = Path("C:/Program Files/Tekla Structures/2026.0/bin/TeklaStructures.exe")
        needles = safe_cleanup_module._registry_needles([target])
        values = [
            (
                r"Software\Microsoft\Windows\CurrentVersion\Installer\Folders",
                r"C:\Program Files\Tekla Structures\2026.0\bin\\",
                "",
            )
        ]

        with patch("launcher.core.safe_cleanup._iter_registry_values", return_value=values):
            items = safe_cleanup_module._scan_installer_registry_base(
                "HKLM",
                object(),
                r"Software\Microsoft\Windows\CurrentVersion\Installer\Folders",
                needles,
                max_depth=1,
                limit=10,
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].kind, "installer_registry_value")
        self.assertEqual(items[0].layer, BLOCKED_LAYER)
        self.assertIn("Windows Installer", items[0].note)

    def test_run_official_uninstaller_prefers_quiet_command(self) -> None:
        uninstaller = OfficialUninstaller(
            id="uninstaller:HKCU:Demo",
            root_name="HKCU",
            registry_key="Software\\Demo",
            display_name="Demo App",
            uninstall_command="normal.exe",
            quiet_uninstall_command="quiet.exe /S",
        )

        with patch("launcher.core.safe_cleanup.subprocess.Popen") as popen:
            run_official_uninstaller(uninstaller)

        popen.assert_called_once_with("quiet.exe /S", shell=True)

    def test_build_cleanup_plan_reports_scan_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("x", encoding="utf-8")
            stages: list[tuple[str, int, int]] = []

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                build_cleanup_plan(
                    LauncherContext.from_paths([target]),
                    state_path=root / "state.json",
                    progress=lambda name, index, total: stages.append((name, index, total)),
                )

        self.assertEqual(stages[0], ("目標身分", 1, 9))
        self.assertEqual(stages[-1], ("工具列紀錄", 9, 9))

    def test_build_cleanup_plan_honors_cancel_token(self) -> None:
        token = ScanCancelToken()
        token.cancel()

        with self.assertRaises(ScanCancelled):
            build_cleanup_plan(LauncherContext.from_paths([Path("C:/Temp/a.txt")]), cancel_token=token)

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
            progress: list[tuple[int, int, str]] = []

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(
                plan,
                {plan.items[0].id},
                quarantine_root=quarantine,
                progress=lambda current, total, label: progress.append((current, total, label)),
            )

            self.assertFalse(target.exists())
            self.assertEqual(result.moved_count, 1)
            self.assertEqual(progress, [(1, 1, "delete_me.txt")])
            self.assertTrue(result.manifest_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["moved"][0]["item"]["label"], "delete_me.txt")
            self.assertEqual(manifest["schema_version"], 1)
            self.assertRegex(manifest["session_id"], r"^[0-9a-f]{32}$")
            self.assertEqual(manifest["moved"][0]["original_path"], str(target))
            self.assertEqual(manifest["moved"][0]["original_sha256"], hashlib.sha256(b"x").hexdigest())
            restore_script = result.quarantine_dir / "Restore.ps1"
            self.assertTrue(restore_script.exists())
            self.assertIn("Skip existing target", restore_script.read_text(encoding="utf-8"))

    def test_apply_registry_cleanup_exports_backup_and_restore_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                with patch("launcher.core.safe_cleanup._delete_registry_value") as delete_registry:
                    result = apply_cleanup_plan(
                        plan,
                        {registry_item.id},
                        include_registry=True,
                        quarantine_root=root / "quarantine",
                    )

            delete_registry.assert_called_once_with(registry_item)
            self.assertEqual(result.registry_deleted_count, 1)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["registry_deleted"][0]["registry_key"], "Software\\Demo")
            self.assertTrue(Path(manifest["registry_deleted"][0]["export_path"]).exists())
            restore_script = result.quarantine_dir / "Restore-Registry.ps1"
            self.assertTrue(restore_script.exists())
            self.assertIn("reg.exe import", restore_script.read_text(encoding="utf-8"))

    def test_restore_registry_items_imports_backup_and_updates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                        quarantine_root=root / "quarantine",
                    )

            with patch("launcher.core.safe_cleanup.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ""
                run.return_value.stderr = ""
                restore_result = restore_registry_items(result.quarantine_dir)

            self.assertEqual(restore_result.restored_count, 1)
            self.assertEqual(restore_result.errors, ())
            run.assert_called_once()
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["registry_deleted"][0]["restored_to"], "registry")
            self.assertIn("restored_at", manifest["registry_deleted"][0])
            sessions = list_quarantine_sessions(root / "quarantine")
            self.assertEqual(sessions[0].registry_deleted_count, 1)

    def test_registry_cleanup_does_not_delete_when_export_fails(self) -> None:
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

        with tempfile.TemporaryDirectory() as tmp:
            with patch("launcher.core.safe_cleanup._export_registry_key", side_effect=RuntimeError("export failed")):
                with patch("launcher.core.safe_cleanup._delete_registry_value") as delete_registry:
                    result = apply_cleanup_plan(
                        plan,
                        {registry_item.id},
                        include_registry=True,
                        quarantine_root=Path(tmp) / "quarantine",
                    )

        delete_registry.assert_not_called()
        self.assertEqual(result.registry_deleted_count, 0)
        self.assertTrue(result.errors)

    def test_restore_quarantine_items_moves_file_back_and_updates_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "restore_me.txt"
            target.write_text("hello", encoding="utf-8")
            quarantine = root / "quarantine"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=quarantine)

            restore_result = restore_quarantine_items(result.quarantine_dir)

            self.assertEqual(restore_result.restored_count, 1)
            self.assertEqual(restore_result.errors, ())
            self.assertTrue(target.exists())
            self.assertEqual(target.read_text(encoding="utf-8"), "hello")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("restored_at", manifest["moved"][0])
            sessions = list_quarantine_sessions(quarantine)
            self.assertEqual(sessions[0].restored_count, 1)

    def test_restore_quarantine_items_skips_conflicting_original_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "conflict.txt"
            target.write_text("old", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=root / "quarantine")
            target.write_text("new", encoding="utf-8")

            restore_result = restore_quarantine_items(result.quarantine_dir)

            self.assertEqual(restore_result.restored_count, 0)
            self.assertTrue(restore_result.errors)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_restore_quarantine_items_can_rename_conflicting_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "conflict.txt"
            target.write_text("old", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=root / "quarantine")
            target.write_text("new", encoding="utf-8")

            restore_result = restore_quarantine_items(result.quarantine_dir, conflict_policy=RestoreConflictPolicy.RENAME)

            restored_files = list(root.glob("conflict.txt.restored-*"))
            self.assertEqual(restore_result.restored_count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")
            self.assertEqual(restored_files[0].read_text(encoding="utf-8"), "old")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["moved"][0]["restore_conflict_policy"], "rename")

    def test_restore_quarantine_items_can_overwrite_conflicting_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "conflict.txt"
            target.write_text("old", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=root / "quarantine")
            target.write_text("new", encoding="utf-8")

            restore_result = restore_quarantine_items(result.quarantine_dir, conflict_policy=RestoreConflictPolicy.OVERWRITE)

            self.assertEqual(restore_result.restored_count, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["moved"][0]["restored_to"], str(target))
            self.assertEqual(manifest["moved"][0]["restore_conflict_policy"], "overwrite")

    def test_delete_quarantine_session_requires_quarantine_root_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "delete_me.txt"
            target.write_text("x", encoding="utf-8")
            quarantine = root / "quarantine"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=quarantine)

            delete_quarantine_session(result.quarantine_dir, root=quarantine)

            self.assertFalse(result.quarantine_dir.exists())

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
