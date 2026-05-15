from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def open_folder(payload: dict[str, Any]) -> dict[str, Any]:
    folder = _folder(payload)
    os.startfile(folder)  # noqa: S606
    return {"type": "artifact", "message": f"已開啟資料夾：{folder}", "path": str(folder)}


def open_powershell(payload: dict[str, Any]) -> dict[str, Any]:
    folder = _folder(payload)
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"
    subprocess.Popen([shell, "-NoExit"], cwd=str(folder))
    return {"type": "artifact", "message": f"已在此開啟 PowerShell：{folder}", "path": str(folder)}


def open_vscode(payload: dict[str, Any]) -> dict[str, Any]:
    folder = _folder(payload)
    code = shutil.which("code") or shutil.which("code.cmd")
    if code is None:
        raise RuntimeError("找不到 VS Code 指令 code。請確認 VS Code 已加入 PATH。")
    subprocess.Popen([code, str(folder)])
    return {"type": "artifact", "message": f"已用 VS Code 開啟：{folder}", "path": str(folder)}


def reveal_first_file(payload: dict[str, Any]) -> dict[str, Any]:
    files = _files(payload)
    if not files:
        raise ValueError("目前沒有選取檔案")
    subprocess.Popen(["explorer.exe", f"/select,{files[0]}"])
    return {"type": "artifact", "message": f"已定位：{files[0]}", "path": str(files[0])}


def open_selected_files(payload: dict[str, Any]) -> dict[str, Any]:
    files = _files(payload)
    if not files:
        raise ValueError("目前沒有選取檔案")
    for path in files[:20]:
        os.startfile(path)  # noqa: S606
    return {"type": "artifact", "message": f"已開啟 {min(len(files), 20)} 個檔案", "count": min(len(files), 20)}


def write_file_list(payload: dict[str, Any]) -> dict[str, Any]:
    folder = _folder(payload)
    files = _files(payload)
    targets = files if files else sorted(path for path in folder.iterdir())
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = folder / f"檔案清單_{stamp}.txt"
    lines = [str(path) for path in targets]
    output.write_text("\n".join(lines), encoding="utf-8")
    return {
        "type": "artifact",
        "message": f"已產生檔案清單：{output}",
        "path": str(output),
        "count": len(lines),
    }


def _folder(payload: dict[str, Any]) -> Path:
    folder = payload["context"].get("folder")
    if not folder:
        raise ValueError("目前沒有資料夾 context")
    return Path(folder)


def _files(payload: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in payload["context"].get("files", [])]

