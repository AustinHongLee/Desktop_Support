from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.app.main import _instance_mutex_name
from launcher.core.paths import app_data_root, default_state_path, project_root, runtime_root


class PathPolicyTests(unittest.TestCase):
    def test_app_data_root_prefers_explicit_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"DESKTOP_SUPPORT_DATA_ROOT": tmp}, clear=False):
                self.assertEqual(app_data_root(), Path(tmp).resolve(strict=False))

    def test_runtime_root_prefers_project_root_env_for_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"DESKTOP_SUPPORT_PROJECT_ROOT": tmp}, clear=False):
                self.assertEqual(runtime_root(), Path(tmp).resolve(strict=False))

    def test_runtime_root_uses_source_checkout_in_development(self) -> None:
        with patch.dict(os.environ, {"DESKTOP_SUPPORT_PROJECT_ROOT": "", "DESKTOP_SUPPORT_DATA_ROOT": ""}, clear=False):
            self.assertEqual(runtime_root(), project_root())

    def test_default_state_path_can_be_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            with patch.dict(os.environ, {"DESKTOP_SUPPORT_STATE_PATH": str(path)}, clear=False):
                self.assertEqual(default_state_path(), path.resolve(strict=False))

    def test_instance_mutex_uses_runtime_root_identity(self) -> None:
        root = Path("C:/StableRuntime")
        digest = hashlib.sha1(str(root.resolve(strict=False)).casefold().encode("utf-8")).hexdigest()[:12]

        with patch("launcher.app.main.runtime_root", return_value=root):
            self.assertEqual(_instance_mutex_name(), f"Local\\EngineeringLauncher_v2_{digest}")


if __name__ == "__main__":
    unittest.main()
