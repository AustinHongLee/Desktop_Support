from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "EngineeringLauncher"
DATA_ROOT_ENV = "DESKTOP_SUPPORT_DATA_ROOT"
PROJECT_ROOT_ENV = "DESKTOP_SUPPORT_PROJECT_ROOT"
STATE_PATH_ENV = "DESKTOP_SUPPORT_STATE_PATH"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def plugin_root() -> Path:
    return project_root() / "launcher" / "plugins"


def app_data_root() -> Path:
    override = _env_path(DATA_ROOT_ENV)
    if override is not None:
        return override
    root = _env_path("LOCALAPPDATA")
    if root is not None:
        return root / APP_DIR_NAME
    return Path.home() / ".engineering_launcher"


def runtime_root() -> Path:
    override = _env_path(PROJECT_ROOT_ENV)
    if override is not None:
        return override
    root = project_root()
    if _looks_like_source_checkout(root):
        return root
    return app_data_root()


def default_state_path() -> Path:
    override = _env_path(STATE_PATH_ENV)
    if override is not None:
        return override
    return app_data_root() / "state.json"


def default_inbox_path() -> Path:
    return app_data_root() / "context_request.json"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return Path(value).expanduser().resolve(strict=False)


def _looks_like_source_checkout(path: Path) -> bool:
    return (path / "launcher" / "app" / "main.py").exists() and (path / "pyproject.toml").exists()
