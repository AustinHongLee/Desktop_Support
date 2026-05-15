from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.plugins.rename_tools.rename_actions import RenameOperation, _apply_operations, apply_rename_plan, create_rename_plan


class RenameActionTests(unittest.TestCase):
    def test_create_and_apply_rename_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "a.txt"
            source.write_text("hello", encoding="utf-8")

            payload = {"context": {"folder": str(folder), "files": [str(source)]}}
            create_rename_plan(payload)

            plan = folder / "rename_plan.csv"
            with plan.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["apply", "original_name", "new_name", "note"])
                writer.writeheader()
                writer.writerow({"apply": "YES", "original_name": "a.txt", "new_name": "b.txt", "note": ""})

            result = apply_rename_plan({"context": {"folder": str(folder), "files": []}})

            self.assertFalse(source.exists())
            self.assertTrue((folder / "b.txt").exists())
            self.assertEqual(result[0]["count"], 1)

    def test_apply_operations_rolls_back_temporary_renames_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            first = folder / "a.txt"
            second = folder / "b.txt"
            first.write_text("a", encoding="utf-8")
            second.write_text("b", encoding="utf-8")
            original_rename = Path.rename

            def guarded_rename(path: Path, target: Path) -> Path:
                if path == second and target.name.startswith(".rename_tmp_"):
                    raise PermissionError("locked")
                return original_rename(path, target)

            with patch.object(Path, "rename", guarded_rename):
                with self.assertRaises(RuntimeError):
                    _apply_operations(
                        [
                            RenameOperation(first, folder / "c.txt"),
                            RenameOperation(second, folder / "d.txt"),
                        ]
                    )

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertFalse(list(folder.glob(".rename_tmp_*")))


if __name__ == "__main__":
    unittest.main()
