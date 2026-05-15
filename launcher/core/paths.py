from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def plugin_root() -> Path:
    return project_root() / "launcher" / "plugins"

