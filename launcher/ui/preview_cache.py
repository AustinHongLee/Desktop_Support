from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreviewCacheKey:
    source: Path
    mtime_ns: int
    size: int


class PdfPreviewCache:
    def __init__(self, temp_dir: Path) -> None:
        self._temp_dir = temp_dir
        self._entries: dict[PreviewCacheKey, Path] = {}

    def preview_path_for(self, source: Path) -> Path:
        key = self._key_for(source)
        cached = self._entries.get(key)
        if cached is not None and cached.exists():
            return cached

        self._temp_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".pdf"
        target = self._temp_dir / f"{uuid.uuid4().hex}{suffix}"
        shutil.copy2(source, target)
        self._entries[key] = target
        return target

    def clear(self) -> None:
        self._entries.clear()

    @staticmethod
    def _key_for(source: Path) -> PreviewCacheKey:
        resolved = source.resolve()
        stat = resolved.stat()
        return PreviewCacheKey(source=resolved, mtime_ns=stat.st_mtime_ns, size=stat.st_size)
