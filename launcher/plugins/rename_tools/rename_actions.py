from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from launcher.windows.clipboard import get_clipboard_text

PLAN_FILE = "rename_plan.csv"
INVALID_NAME_CHARS = set('<>:"/\\|?*')
APPLY_VALUES = {"yes", "y", "1", "true", "是", "套用"}


def rename_selected_from_clipboard(payload: dict[str, Any]) -> dict[str, Any]:
    files = _files(payload)
    if len(files) != 1:
        raise ValueError("請只選取一個檔案")
    source = files[0]
    clipboard = get_clipboard_text().strip()
    if not clipboard:
        raise ValueError("剪貼簿沒有文字")

    new_name = _normalize_clipboard_name(clipboard, source.suffix)
    target = source.with_name(new_name)
    _validate_target(source, target)
    source.rename(target)
    return {"type": "artifact", "message": f"已更名：{source.name} -> {target.name}", "path": str(target)}


def create_rename_plan(payload: dict[str, Any]) -> dict[str, Any]:
    folder = _folder(payload)
    files = _files(payload)
    targets = files if files else sorted((path for path in folder.iterdir() if path.is_file()), key=lambda path: path.name.lower())
    if not targets:
        raise ValueError("沒有可建立更名表的檔案")

    plan = folder / PLAN_FILE
    with plan.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["apply", "original_name", "new_name", "note"])
        writer.writeheader()
        for path in targets:
            writer.writerow({"apply": "", "original_name": path.name, "new_name": path.name, "note": ""})

    return {
        "type": "artifact",
        "message": f"已產生批次更名表：{plan}。編輯 new_name，並在 apply 欄填 YES 後再套用。",
        "path": str(plan),
        "count": len(targets),
    }


def apply_rename_plan(payload: dict[str, Any]) -> list[dict[str, Any]]:
    folder = _folder(payload)
    plan = folder / PLAN_FILE
    if not plan.exists():
        raise FileNotFoundError(f"找不到 {plan}")

    operations = _read_plan(folder, plan)
    if not operations:
        return [{"type": "message", "message": "沒有 apply=YES 的更名列，未執行任何更名。"}]
    _validate_operations(operations)
    _apply_operations(operations)
    return [
        {"type": "artifact", "message": f"已套用 {len(operations)} 筆更名", "count": len(operations)},
        *[
            {"type": "message", "message": f"{operation.source.name} -> {operation.target.name}"}
            for operation in operations
        ],
    ]


@dataclass(frozen=True)
class RenameOperation:
    source: Path
    target: Path


def _read_plan(folder: Path, plan: Path) -> list[RenameOperation]:
    operations: list[RenameOperation] = []
    with plan.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"apply", "original_name", "new_name"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError("rename_plan.csv 必須包含 apply, original_name, new_name 欄位")
        for row in reader:
            if str(row.get("apply", "")).strip().lower() not in APPLY_VALUES:
                continue
            original_name = str(row.get("original_name", "")).strip()
            new_name = str(row.get("new_name", "")).strip()
            if not original_name or not new_name:
                raise ValueError("original_name 與 new_name 不可空白")
            source = folder / original_name
            target = folder / new_name
            if source == target:
                continue
            operations.append(RenameOperation(source=source, target=target))
    return operations


def _validate_operations(operations: list[RenameOperation]) -> None:
    sources = {operation.source for operation in operations}
    targets: set[Path] = set()
    for operation in operations:
        _validate_file_name(operation.target.name)
        if not operation.source.exists():
            raise FileNotFoundError(f"來源不存在：{operation.source}")
        if operation.target in targets:
            raise FileExistsError(f"目標檔名重複：{operation.target.name}")
        targets.add(operation.target)
        if operation.target.exists() and operation.target not in sources:
            raise FileExistsError(f"目標已存在：{operation.target}")


def _apply_operations(operations: list[RenameOperation]) -> None:
    staged: list[tuple[Path, Path, Path]] = []
    finalized: list[tuple[Path, Path, Path]] = []
    try:
        for operation in operations:
            temporary = operation.source.with_name(f".rename_tmp_{uuid.uuid4().hex}{operation.source.suffix}")
            operation.source.rename(temporary)
            staged.append((operation.source, operation.target, temporary))

        for source, target, temporary in staged:
            temporary.rename(target)
            finalized.append((source, target, temporary))
    except Exception as exc:
        _rollback_operations(staged, finalized)
        raise RuntimeError(f"更名失敗，已嘗試還原檔案狀態：{exc}") from exc


def _rollback_operations(staged: list[tuple[Path, Path, Path]], finalized: list[tuple[Path, Path, Path]]) -> None:
    for source, target, _temporary in reversed(finalized):
        if target.exists() and not source.exists():
            target.rename(source)
    for source, _target, temporary in reversed(staged):
        if temporary.exists() and not source.exists():
            temporary.rename(source)


def _normalize_clipboard_name(text: str, original_suffix: str) -> str:
    name = Path(text).name.strip()
    if not name:
        raise ValueError("剪貼簿文字不是有效檔名")
    _validate_file_name(name)
    if Path(name).suffix:
        return name
    return f"{name}{original_suffix}"


def _validate_target(source: Path, target: Path) -> None:
    _validate_file_name(target.name)
    if target == source:
        raise ValueError("新檔名與原檔名相同")
    if target.exists():
        raise FileExistsError(f"目標已存在：{target}")


def _validate_file_name(name: str) -> None:
    if any(char in INVALID_NAME_CHARS for char in name):
        raise ValueError(f"檔名包含 Windows 不允許的字元：{name}")
    if name in {".", ".."}:
        raise ValueError(f"無效檔名：{name}")


def _folder(payload: dict[str, Any]) -> Path:
    folder = payload["context"].get("folder")
    if not folder:
        raise ValueError("目前沒有資料夾 context")
    return Path(folder)


def _files(payload: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in payload["context"].get("files", [])]
