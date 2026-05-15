from __future__ import annotations

from pathlib import Path
from typing import Any

from launcher.plugins._common.payload_utils import files as payload_files
from launcher.plugins._common.payload_utils import folder as payload_folder
from launcher.windows.clipboard import set_clipboard_text


def copy_full_paths(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = _files(payload)
    text = "\n".join(str(path) for path in files)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製 {len(files)} 個完整路徑",
            "count": len(files),
        }
    ]


def copy_file_names(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = _files(payload)
    text = "\n".join(path.name for path in files)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製 {len(files)} 個檔名",
            "count": len(files),
        }
    ]


def copy_selected_base_names(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = _files(payload)
    text = "\n".join(path.stem for path in files)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製 {len(files)} 個不含副檔名的檔名",
            "count": len(files),
        }
    ]


def copy_selection(payload: dict[str, Any]) -> list[dict[str, Any]]:
    selected = payload_files(payload)
    if not selected:
        raise ValueError("此指令需要至少一個選取檔案")
    mode = str(payload.get("options", {}).get("mode") or "path")
    text = "\n".join(_path_text(path, mode) for path in selected)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製 {len(selected)} 個選取項目（{_mode_label(mode)}）",
            "count": len(selected),
            "mode": mode,
        }
    ]


def copy_folder_path(payload: dict[str, Any]) -> list[dict[str, Any]]:
    folder = payload["context"].get("folder")
    if not folder:
        raise ValueError("No folder in current context")
    set_clipboard_text(str(Path(folder)))
    return [
        {
            "type": "artifact",
            "message": "已複製目前資料夾",
            "path": str(Path(folder)),
        }
    ]


def copy_folder_listing(payload: dict[str, Any]) -> list[dict[str, Any]]:
    target = payload_folder(payload)
    options = payload.get("options", {})
    include = str(options.get("include") or "all")
    mode = str(options.get("mode") or "name")
    if include == "files":
        paths = sorted((path for path in target.iterdir() if path.is_file()), key=lambda path: path.name.lower())
    else:
        paths = sorted(target.iterdir(), key=lambda path: path.name.lower())
    text = "\n".join(_path_text(path, mode) for path in paths)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製資料夾清單 {len(paths)} 筆（{_include_label(include)} / {_mode_label(mode)}）",
            "count": len(paths),
            "include": include,
            "mode": mode,
        }
    ]


def copy_folder_item_names(payload: dict[str, Any]) -> list[dict[str, Any]]:
    folder = _folder(payload)
    items = sorted(folder.iterdir(), key=lambda path: path.name.lower())
    text = "\n".join(path.name for path in items)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製目前資料夾 {len(items)} 個項目名稱",
            "count": len(items),
        }
    ]


def copy_folder_file_names(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = _folder_files(payload)
    text = "\n".join(path.name for path in files)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製目前資料夾 {len(files)} 個檔名",
            "count": len(files),
        }
    ]


def copy_folder_file_base_names(payload: dict[str, Any]) -> list[dict[str, Any]]:
    files = _folder_files(payload)
    text = "\n".join(path.stem for path in files)
    set_clipboard_text(text)
    return [
        {
            "type": "artifact",
            "message": f"已複製目前資料夾 {len(files)} 個不含副檔名的檔名",
            "count": len(files),
        }
    ]


def _files(payload: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in payload["context"].get("files", [])]


def _folder(payload: dict[str, Any]) -> Path:
    folder = payload["context"].get("folder")
    if not folder:
        raise ValueError("目前沒有資料夾 context")
    return Path(folder)


def _folder_files(payload: dict[str, Any]) -> list[Path]:
    return sorted((path for path in _folder(payload).iterdir() if path.is_file()), key=lambda path: path.name.lower())


def _path_text(path: Path, mode: str) -> str:
    if mode == "name":
        return path.name
    if mode == "basename":
        return path.stem
    if mode == "path":
        return str(path)
    raise ValueError(f"不支援的複製模式：{mode}")


def _mode_label(mode: str) -> str:
    return {
        "path": "完整路徑",
        "name": "名稱",
        "basename": "不含副檔名",
    }.get(mode, mode)


def _include_label(include: str) -> str:
    return {
        "all": "全部項目",
        "files": "只含檔案",
    }.get(include, include)
