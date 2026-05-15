from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LauncherContext:
    """Snapshot of the user's current working context."""

    folder: Path | None = None
    files: tuple[Path, ...] = field(default_factory=tuple)
    source: str = "manual"

    @classmethod
    def empty(cls) -> "LauncherContext":
        return cls()

    @classmethod
    def from_paths(
        cls,
        paths: list[str | Path],
        *,
        folder: str | Path | None = None,
        source: str = "manual",
    ) -> "LauncherContext":
        resolved_files = tuple(Path(path) for path in paths)
        resolved_folder = Path(folder) if folder is not None else cls._infer_folder(resolved_files)
        return cls(folder=resolved_folder, files=resolved_files, source=source)

    @staticmethod
    def _infer_folder(files: tuple[Path, ...]) -> Path | None:
        if not files:
            return None
        first = files[0]
        return first if first.is_dir() else first.parent

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def extensions(self) -> set[str]:
        return {path.suffix.lower() for path in self.files if path.suffix}

    def to_payload(self) -> dict[str, Any]:
        return {
            "folder": str(self.folder) if self.folder else None,
            "files": [str(path) for path in self.files],
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LauncherContext":
        folder = payload.get("folder")
        files = payload.get("files") or []
        return cls(
            folder=Path(folder) if folder else None,
            files=tuple(Path(path) for path in files),
            source=str(payload.get("source") or "worker"),
        )

