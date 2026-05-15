# 指令面板擴充與延伸 — Codex 修改指令書 v0.1

> 對照基準：`launcher/plugins/**/actions.json`、`launcher/core/action_model.py`、`launcher/workers/worker_host.py`
> 適用版本：Engineering Launcher 0.1.x（pyproject.toml 名稱 `engineering-launcher`）
> 文件用途：交付給 Codex / Claude Code agent 執行的工作清單。每個區塊都列「目的、檔案異動、關鍵程式碼、驗收條件」。

---

## 0. 通則 — 開工前先讀

### 0.1 既有契約（不可破壞）

- Worker 入口簽章：`entry(payload: dict) -> dict | list[dict] | None`
- `payload` 結構：
  ```python
  {
    "action": <ActionDefinition.to_payload()>,
    "context": {"folder": str | None, "files": [str, ...], "source": str},
    "options": {}
  }
  ```
- 事件字典：`{"type": "message"|"artifact"|"error", "message": str, ...}`，由 `worker_host._events_from_result` 輸出。
- 新指令一律走 `command.type = "python_module"`，避免 UI 對話框型指令（保留給已存在的 rename / iso_pdf）。
- 新增 action 時，`id` 命名規則沿用 `<plugin_id>.<verb>`；`category` 用中文短詞（剪貼簿、檔案、PDF、更名、ISO、診斷……）。

### 0.2 共用 helper（建議新增一個位置）

新增 `launcher/plugins/_common/payload_utils.py`：

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

def files(payload: dict[str, Any]) -> list[Path]:
    return [Path(p) for p in payload["context"].get("files", [])]

def folder(payload: dict[str, Any]) -> Path:
    f = payload["context"].get("folder")
    if not f:
        raise ValueError("此指令需要 context 資料夾")
    return Path(f)

def filter_ext(paths: list[Path], *exts: str) -> list[Path]:
    s = {e.lower() for e in exts}
    return [p for p in paths if p.suffix.lower() in s]
```

之後所有新 worker 用 `from launcher.plugins._common.payload_utils import files, folder, filter_ext`。`_common` 不放 `plugin.json`，所以不會被 registry 載入。

### 0.3 驗收原則

- 每新增一個 action 必須附 `tests/test_<plugin>_<verb>.py`，至少一個 happy path + 一個 raises ValueError 的 negative case。
- 不准在 worker 內呼叫 PyQt（worker 是子程序、無 Qt event loop）。對話需求一律由 UI 層 dialog 處理，再把結果丟給 worker（如同 rename_dialog 的做法）。
- High-risk action 都要設 `"risk": "high"` 並避免「沒有 dry-run」的破壞性行為。預設應產生計畫檔（CSV）→ 使用者確認 → 套用，比照 rename 流程。

---

## 區塊 A — 清理沒意義的工具

### A1. 隱藏 diagnostics 測試用指令到 developer mode

**目的**：`diagnostics.wait_cancel`、`diagnostics.wait_timeout` 對一般使用者沒意義，但開發階段仍需保留。

**檔案異動**：

- `launcher/core/state_store.py`：在 `AppStateStore` 增加 `developer_mode: bool` property，預設 `False`，從 `state.json["developer_mode"]` 讀。
- `launcher/core/registry.py`：在 `all_actions` 之外新增 `def visible_actions(self, *, developer_mode: bool) -> list[ActionDefinition]`，過濾掉 `plugin_id == "diagnostics"` 且 `id` 結尾為 `.wait_cancel|.wait_timeout` 的兩條。`diagnostics.echo_context` 維持公開（一般使用者偵錯也用得到）。
- `launcher/ui/command_palette.py`、`launcher/ui/dock_window.py`：呼叫端改用 `visible_actions(developer_mode=state.developer_mode)`。
- `launcher/ui/preferences_dialog.py`：加一個 checkbox「顯示開發者測試指令」綁到 `state.developer_mode`。

**關鍵程式碼**：

```python
# registry.py
_DEV_ONLY_IDS = {"diagnostics.wait_cancel", "diagnostics.wait_timeout"}

def visible_actions(self, *, developer_mode: bool) -> list[ActionDefinition]:
    actions = self.all_actions()
    if developer_mode:
        return actions
    return [a for a in actions if a.id not in _DEV_ONLY_IDS]
```

**驗收**：`test_registry.py` 新增 `test_visible_actions_hides_dev_only`、`test_visible_actions_shows_dev_only_when_enabled`。

---

### A2. 合併過度切分的 copy 指令

**目的**：copy_utils 目前 7 條 action，使用者要從面板挑選成本太高。降為 2 條主指令 + UI modifier 選項。

**檔案異動**：

- 廢棄 actions（保留 entry function 不刪，給 backward compat）：
  - `copy.file_names`
  - `copy.selected_base_names`
  - `copy.folder_item_names`
  - `copy.folder_file_names`
  - `copy.folder_file_base_names`
- 新 actions：
  - `copy.selection`（取代前 3 個）
  - `copy.folder_listing`（取代後 3 個）
- 兩條都走新的 worker entry `copy_selection` / `copy_folder_listing`，從 `payload["options"]` 讀使用者選擇：`mode = "path"|"name"|"basename"`、`include = "all"|"files"`。
- UI：在 `launcher/ui/command_palette.py` 攔截這兩個 action 的執行，先彈一個輕量選項對話框（QDialog 含 2~3 個 QRadioButton），把選擇寫入 `options` 再交給 runner。
  - 預設選項：path / all。
  - 對話框可記憶上次選擇到 `state.json["copy_last_choice"]`。
- 沿用做法：保留鍵盤捷徑 `Ctrl+Enter` 跳過對話框，直接走預設。

**關鍵程式碼**：

```jsonc
// launcher/plugins/copy_utils/actions.json — 新增（其餘舊條目刪除）
{
  "id": "copy.selection",
  "title": "複製選取項目",
  "category": "剪貼簿",
  "description": "依模式複製選取項目的路徑/檔名/不含副檔名檔名。",
  "icon": "copy",
  "accepts": {"min_files": 1},
  "command": {"type": "python_module",
              "module": "launcher.plugins.copy_utils.copy_paths",
              "entry": "copy_selection"}
}
```

```python
# copy_paths.py — 新 entry
def copy_selection(payload):
    paths = files(payload)
    mode = payload.get("options", {}).get("mode", "path")
    if mode == "name":      text = "\n".join(p.name for p in paths)
    elif mode == "basename":text = "\n".join(p.stem for p in paths)
    else:                   text = "\n".join(str(p) for p in paths)
    set_clipboard_text(text)
    return [{"type": "artifact",
             "message": f"已複製 {len(paths)} 個項目（mode={mode}）",
             "count": len(paths)}]
```

**驗收**：
- `test_copy_paths.py` 補三組 parametrize（mode=path/name/basename）；folder_listing 同樣補三組（include=all/files + mode=…）。
- Migration：第一次啟動偵測 `state.recent_actions` 有舊 id 時，自動映射成新 id（簡單字典）。

---

### A3. 移除功能重疊的「定位第一個選取檔案」（合併到「開啟目前資料夾」）

**目的**：`system.reveal_first_file` 與 `system.open_folder` 在多檔情境下行為非常接近，使用者面板上易混淆。

**檔案異動**：

- `system_tools/actions.json`：刪除 `system.reveal_first_file`。
- `system_tools/actions.json`：將 `system.open_folder` 的 entry 改為 `open_folder_or_reveal`，accepts 同時允許 `requires_folder` 或 `min_files >= 1`（不過 ActionAccepts 是 AND 邏輯，這裡只 require_folder=True 即可，因為 context 在有 file 時 folder 也會被推導出來）。
- `system_actions.py` 新 entry：

```python
def open_folder_or_reveal(payload):
    paths = files(payload)
    if paths:
        subprocess.Popen(["explorer", "/select,", str(paths[0])])
        return {"type": "message", "message": f"已定位 {paths[0].name}"}
    target = folder(payload)
    subprocess.Popen(["explorer", str(target)])
    return {"type": "message", "message": f"已開啟 {target}"}
```

**驗收**：`test_system_actions.py` 補 `test_open_folder_or_reveal_selects_file` / `test_open_folder_or_reveal_falls_back_to_folder`，用 `monkeypatch.setattr(subprocess, "Popen", ...)` 攔截。

---

## 區塊 B — A 組高頻新指令

> 新指令統一放在 `launcher/plugins/file_ops/`（新建 plugin）與既有 `pdf_tools`。
> `file_ops/plugin.json`：`{"id": "file_ops", "title": "檔案操作"}`

### B1. PDF 合併（pdf_tools）

**actions.json 加一條**：

```jsonc
{
  "id": "pdf.merge",
  "title": "PDF 合併",
  "category": "PDF",
  "description": "依選取順序合併多個 PDF；可由 UI 拖拉排序。",
  "icon": "files",
  "risk": "medium",
  "accepts": {"extensions": [".pdf"], "min_files": 2},
  "command": {"type": "python_module",
              "module": "launcher.plugins.pdf_tools.pdf_actions",
              "entry": "merge_pdfs"}
}
```

**worker 關鍵碼**：

```python
def merge_pdfs(payload):
    pdfs = filter_ext(files(payload), ".pdf")
    if len(pdfs) < 2:
        raise ValueError("請至少選取 2 份 PDF")
    order = payload.get("options", {}).get("order")  # UI 端提供的排序 list[int]
    if order:
        pdfs = [pdfs[i] for i in order]
    out = pdfs[0].with_name(f"merged_{len(pdfs)}files.pdf")
    writer = PdfWriter()
    for p in pdfs:
        for page in PdfReader(str(p)).pages:
            writer.add_page(page)
    with out.open("wb") as fh:
        writer.write(fh)
    return [{"type": "artifact", "message": f"已合併 → {out.name}", "path": str(out)}]
```

**UI**：新增 `launcher/ui/pdf_merge_dialog.py`，類似 rename_dialog：表格顯示 `序、檔名、頁數`，上下按鈕可移動 row 順序，OK 把 `order=[索引...]` 放進 options。命令類型維持 `python_module`；對話框走 UI 攔截派工。

**驗收**：`test_pdf_actions.py` 補 `test_merge_pdfs_uses_order`、`test_merge_pdfs_requires_two`。

---

### B2. PDF 旋轉頁面（pdf_tools）

```jsonc
{
  "id": "pdf.rotate",
  "title": "PDF 旋轉頁面",
  "category": "PDF",
  "description": "對選取 PDF 旋轉所有頁或指定頁範圍（90/180/270）。",
  "accepts": {"extensions": [".pdf"], "min_files": 1},
  "risk": "medium",
  "command": {"type": "python_module",
              "module": "launcher.plugins.pdf_tools.pdf_actions",
              "entry": "rotate_pdfs"}
}
```

```python
def rotate_pdfs(payload):
    deg = int(payload.get("options", {}).get("degrees", 90))
    assert deg in (90, 180, 270)
    page_range = payload.get("options", {}).get("pages")  # None 或 (start, end) 0-based inclusive
    results = []
    for pdf in filter_ext(files(payload), ".pdf"):
        reader = PdfReader(str(pdf)); writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if page_range is None or page_range[0] <= i <= page_range[1]:
                page.rotate(deg)
            writer.add_page(page)
        out = pdf.with_name(f"{pdf.stem}_rot{deg}.pdf")
        with out.open("wb") as fh: writer.write(fh)
        results.append({"type": "artifact", "message": f"{pdf.name} → {out.name}", "path": str(out)})
    return results
```

UI 給三顆按鈕（90/180/270）+ 頁範圍輸入。

---

### B3. 檔名 regex 取代（file_ops）

```jsonc
{
  "id": "fileops.regex_rename",
  "title": "檔名 Regex 取代",
  "category": "更名",
  "description": "輸入 pattern + replacement，產生 rename_plan.csv 供確認後套用。",
  "accepts": {"requires_folder": true},
  "risk": "medium",
  "command": {"type": "python_module",
              "module": "launcher.plugins.file_ops.regex_rename",
              "entry": "build_regex_plan"}
}
```

**設計重點**：不直接改檔名，先產 `rename_plan.csv`，使用者再呼叫 `rename.apply_plan` 套用。複用既有 rename 套用流程。

```python
import re, csv
def build_regex_plan(payload):
    opts = payload.get("options", {})
    pattern, replacement = opts["pattern"], opts.get("replacement", "")
    rx = re.compile(pattern)
    target = folder(payload)
    rows = []
    for p in sorted(target.iterdir()):
        if not p.is_file(): continue
        new = rx.sub(replacement, p.name)
        if new != p.name:
            rows.append({"src": p.name, "dst": new, "apply": "YES"})
    plan = target / "rename_plan.csv"
    with plan.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["src", "dst", "apply"])
        w.writeheader(); w.writerows(rows)
    return [{"type": "artifact",
             "message": f"產生 {len(rows)} 筆更名計畫 → {plan.name}",
             "path": str(plan)}]
```

UI：在 dock 或對話框輸入 pattern / replacement（兩個 QLineEdit），即時預覽前 5 個 match 結果。

---

### B4. 加前綴 / 後綴 / 序號重編（file_ops）

把三件事合成一條 action `fileops.batch_label`，options 描述具體模式：

```python
def build_label_plan(payload):
    opts = payload.get("options", {})
    mode = opts["mode"]            # "prefix" | "suffix" | "sequence"
    text = opts.get("text", "")    # prefix/suffix 用
    start = int(opts.get("start", 1))
    width = int(opts.get("width", 3))
    target = folder(payload)
    plan_rows = []
    for i, p in enumerate(sorted(target.iterdir()), start=start):
        if not p.is_file(): continue
        stem, ext = p.stem, p.suffix
        if mode == "prefix":   new = f"{text}{stem}{ext}"
        elif mode == "suffix": new = f"{stem}{text}{ext}"
        elif mode == "sequence": new = f"{text}{i:0{width}d}{ext}"
        else: raise ValueError(f"unknown mode: {mode}")
        if new != p.name:
            plan_rows.append({"src": p.name, "dst": new, "apply": "YES"})
    # 寫入 rename_plan.csv，同 B3
```

UI：QComboBox 切 mode；text / start / width 對應顯示。

---

### B5. 依副檔名分桶（file_ops）

```jsonc
{
  "id": "fileops.bucket_by_ext",
  "title": "依副檔名分桶到子資料夾",
  "category": "整理",
  "description": "把目前資料夾的檔案依副檔名搬到 <ext>/ 子資料夾。",
  "accepts": {"requires_folder": true},
  "risk": "high",
  "command": {"type": "python_module",
              "module": "launcher.plugins.file_ops.bucket",
              "entry": "bucket_by_ext"}
}
```

```python
import shutil
def bucket_by_ext(payload):
    dry_run = bool(payload.get("options", {}).get("dry_run", True))
    target = folder(payload)
    moved = []
    for p in target.iterdir():
        if not p.is_file(): continue
        sub = target / (p.suffix.lower().lstrip(".") or "_no_ext")
        sub.mkdir(exist_ok=True)
        dest = sub / p.name
        if dry_run:
            moved.append({"type": "message", "message": f"[預覽] {p.name} → {sub.name}/"})
        else:
            shutil.move(str(p), str(dest))
            moved.append({"type": "artifact", "message": f"{p.name} → {sub.name}/", "path": str(dest)})
    return moved or [{"type": "message", "message": "沒有可分桶的檔案"}]
```

**UI 規則**：第一次呼叫 `dry_run=True`，把預覽顯示在 JobMonitor，使用者按「確認執行」再以 `dry_run=False` 重跑。這是新增的安全模式樣板，後續 high-risk action 都仿用。

---

### B6. 依日期分桶（file_ops）

同 B5，但 sub 為 `YYYY-MM`，來源時間取 `p.stat().st_mtime`。

```python
from datetime import datetime
sub = target / datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")
```

---

### B7. 產生資料夾樹 TXT（file_ops）

```jsonc
{
  "id": "fileops.tree_txt",
  "title": "產生資料夾樹 TXT",
  "category": "報告",
  "accepts": {"requires_folder": true},
  "command": {"type": "python_module",
              "module": "launcher.plugins.file_ops.tree",
              "entry": "write_tree_txt"}
}
```

```python
def write_tree_txt(payload):
    depth = int(payload.get("options", {}).get("depth", 3))
    root = folder(payload)
    out = root / "tree.txt"
    lines = []
    def walk(p, d):
        if d > depth: return
        for child in sorted(p.iterdir()):
            lines.append("  " * d + ("📁 " if child.is_dir() else "") + child.name)
            if child.is_dir(): walk(child, d + 1)
    walk(root, 0)
    out.write_text("\n".join(lines), encoding="utf-8")
    return [{"type": "artifact", "message": f"已輸出 {len(lines)} 行 → tree.txt", "path": str(out)}]
```

---

### B8. 檔案 hash 複製到剪貼簿（file_ops）

```jsonc
{
  "id": "fileops.hash_clipboard",
  "title": "複製檔案 SHA-256 到剪貼簿",
  "category": "剪貼簿",
  "accepts": {"min_files": 1, "max_files": 16}
}
```

```python
import hashlib
def hash_to_clipboard(payload):
    rows = []
    for p in files(payload):
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        rows.append(f"{h.hexdigest()}  {p.name}")
    set_clipboard_text("\n".join(rows))
    return [{"type": "artifact", "message": f"已複製 {len(rows)} 個 hash", "count": len(rows)}]
```

---

### B9. 統計資料夾大小 / 副檔名分布（file_ops）

```python
from collections import Counter
def folder_stats(payload):
    target = folder(payload)
    by_ext = Counter()
    total_size = 0
    file_count = 0
    for p in target.rglob("*"):
        if p.is_file():
            file_count += 1
            total_size += p.stat().st_size
            by_ext[p.suffix.lower() or "_no_ext"] += 1
    summary = (f"總計 {file_count} 個檔案，共 {total_size / 1024 / 1024:.1f} MB\n"
               + "\n".join(f"  {ext or '(無)':<10} {n}" for ext, n in by_ext.most_common(10)))
    set_clipboard_text(summary)
    return [{"type": "message", "message": summary}]
```

---

### A 組驗收清單

- [ ] `tests/test_file_ops_*.py` 涵蓋 B3–B9 各自至少一個 happy path。
- [ ] B5/B6 額外有 `dry_run=True` 與 `dry_run=False` 兩組測試。
- [ ] `tests/test_pdf_actions.py` 補 merge / rotate。
- [ ] `launcher/plugins/file_ops/plugin.json` 與 `actions.json` 通過 `ActionRegistry.load()` 不產 issue（在 `test_registry.py` 加一個 smoke test）。

---

## 區塊 C — B 組工程專用

> 都放在新 plugin `launcher/plugins/engineering/`。
> 此區所有 worker 都得處理「外部工具不存在」的情境：先用 `shutil.which`/路徑檢查，缺工具就 raise 並提示安裝指令。

### C1. DWG 批次轉 PDF（透過 ODA File Converter）

**前置**：使用者需自行安裝 ODA File Converter（免費）。把可執行檔路徑放 `state.json["oda_converter_path"]`，於 Preferences 對話框新增欄位。

```jsonc
{
  "id": "engineering.dwg_to_pdf",
  "title": "DWG → PDF（批次）",
  "category": "工程",
  "description": "透過 ODA File Converter 將選取 DWG 轉成 PDF。",
  "accepts": {"extensions": [".dwg"], "min_files": 1},
  "risk": "medium",
  "command": {"type": "python_module",
              "module": "launcher.plugins.engineering.dwg",
              "entry": "dwg_to_pdf"}
}
```

```python
import subprocess, tempfile, shutil
def dwg_to_pdf(payload):
    exe = payload.get("options", {}).get("oda_converter_path") or _read_state_oda_path()
    if not exe or not Path(exe).exists():
        raise ValueError("尚未設定 ODA File Converter 路徑（Preferences → 工程工具）")
    src_files = filter_ext(files(payload), ".dwg")
    with tempfile.TemporaryDirectory() as in_dir, tempfile.TemporaryDirectory() as out_dir:
        for p in src_files:
            shutil.copy(p, Path(in_dir) / p.name)
        # ODA cli: ODAFileConverter <input> <output> ACAD2018 PDF 0 1 "*.DWG"
        subprocess.run([exe, in_dir, out_dir, "ACAD2018", "PDF", "0", "1", "*.DWG"], check=True)
        results = []
        for pdf in Path(out_dir).glob("*.pdf"):
            target = src_files[0].parent / pdf.name
            shutil.move(pdf, target)
            results.append({"type": "artifact", "message": f"{pdf.name}", "path": str(target)})
    return results
```

**驗收**：用 `monkeypatch` 假冒 `subprocess.run`，測試（1）缺工具 raise，（2）有工具會把輸出複製到原資料夾。

---

### C2. Excel ISO 清單比對（engineering）

**目的**：把兩個 ISO Excel 的「管線號碼」欄比對差集，輸出 `compare_<a>_vs_<b>.xlsx`。

```jsonc
{
  "id": "engineering.iso_list_compare",
  "title": "ISO 清單差異比對",
  "category": "ISO",
  "description": "選取兩個 .xlsx/.xlsm/.csv，輸出差集與交集報表。",
  "accepts": {"extensions": [".xlsx", ".xlsm", ".csv"], "min_files": 2, "max_files": 2},
  "command": {"type": "python_module",
              "module": "launcher.plugins.engineering.iso_compare",
              "entry": "compare_iso_lists"}
}
```

```python
import openpyxl
def _read_keys(path: Path, key_col: str = "管線號碼") -> set[str]:
    if path.suffix.lower() == ".csv":
        import csv
        with path.open(encoding="utf-8-sig") as fh:
            rdr = csv.DictReader(fh)
            return {str(row[key_col]).strip() for row in rdr if row.get(key_col)}
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    header = [c.value for c in next(ws.iter_rows(max_row=1))]
    idx = header.index(key_col)
    return {str(row[idx]).strip() for row in ws.iter_rows(min_row=2, values_only=True) if row[idx]}

def compare_iso_lists(payload):
    a, b = files(payload)[:2]
    set_a, set_b = _read_keys(a), _read_keys(b)
    out = a.parent / f"compare_{a.stem}_vs_{b.stem}.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "only_in_a"; [wb["only_in_a"].append([x]) for x in sorted(set_a - set_b)]
    wb.create_sheet("only_in_b"); [wb["only_in_b"].append([x]) for x in sorted(set_b - set_a)]
    wb.create_sheet("intersection"); [wb["intersection"].append([x]) for x in sorted(set_a & set_b)]
    wb.save(out)
    return [{"type": "artifact",
             "message": f"差異 a-b={len(set_a - set_b)}, b-a={len(set_b - set_a)}, 交集={len(set_a & set_b)}",
             "path": str(out)}]
```

UI：optional — 允許使用者指定 key_col 名稱（預設「管線號碼」，可下拉切「sort」「流水號」）。

---

### C3. PDF OCR 轉可搜尋（engineering）

**前置**：複用 ISO workbench 既有的 RapidOCR；缺套件時 raise。

```python
# 偷懶版（純文字 sidecar），確保不破壞原 PDF 排版
def ocr_pdf_to_text(payload):
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        raise ValueError("尚未安裝 RapidOCR，請執行 scripts\\install_ocr.ps1")
    import fitz  # PyMuPDF
    rocr = RapidOCR()
    results = []
    for pdf in filter_ext(files(payload), ".pdf"):
        doc = fitz.open(pdf); pages = []
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=200)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            res, _ = rocr(arr)
            text = "\n".join(seg[1] for seg in (res or []))
            pages.append(f"### page {i}\n{text}")
        out = pdf.with_suffix(".ocr.txt")
        out.write_text("\n\n".join(pages), encoding="utf-8")
        results.append({"type": "artifact", "message": f"{pdf.name} → {out.name}", "path": str(out)})
    return results
```

> 真正的「可搜尋 PDF」需要 OCR 後寫回 invisible text layer。若要做完整版，建議走 `ocrmypdf`（外部 CLI），架構與 C1 ODA 相同：先檢查路徑、再 subprocess。第一版交付建議只做純文字 sidecar，標題改成「PDF OCR 文字輸出」。

---

### C4. 兩資料夾差異比對（engineering）

```python
import hashlib
def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()

def diff_two_folders(payload):
    # 預期 options.left, options.right 為兩個資料夾路徑；UI 端設定。
    opts = payload.get("options", {})
    left, right = Path(opts["left"]), Path(opts["right"])
    def index(root):
        return {str(p.relative_to(root)): p for p in root.rglob("*") if p.is_file()}
    li, ri = index(left), index(right)
    only_left, only_right, diff = [], [], []
    for rel in sorted(set(li) | set(ri)):
        if rel not in ri: only_left.append(rel)
        elif rel not in li: only_right.append(rel)
        elif _hash_file(li[rel]) != _hash_file(ri[rel]): diff.append(rel)
    out = (left.parent if left.parent == right.parent else left) / f"diff_{left.name}_vs_{right.name}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["status", "path"])
        for r in only_left: w.writerow(["only_left", r])
        for r in only_right: w.writerow(["only_right", r])
        for r in diff: w.writerow(["differ", r])
    return [{"type": "artifact",
             "message": f"only_left={len(only_left)}, only_right={len(only_right)}, differ={len(diff)}",
             "path": str(out)}]
```

UI：對話框讓使用者把 dock 拖入兩個資料夾，或由 dock context + 「比對至 …」按鈕。

---

### C5. 找重複檔案（engineering）

```python
def find_duplicates(payload):
    target = folder(payload)
    buckets: dict[int, list[Path]] = {}
    for p in target.rglob("*"):
        if p.is_file(): buckets.setdefault(p.stat().st_size, []).append(p)
    groups = []
    for size, paths in buckets.items():
        if len(paths) < 2: continue
        by_hash: dict[str, list[Path]] = {}
        for p in paths: by_hash.setdefault(_hash_file(p), []).append(p)
        for h, dups in by_hash.items():
            if len(dups) >= 2: groups.append((h, size, dups))
    out = target / "duplicates.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["hash", "size", "path"])
        for h, sz, dups in groups:
            for p in dups: w.writerow([h, sz, str(p)])
    return [{"type": "artifact",
             "message": f"找到 {sum(len(d) for _,_,d in groups)} 個重複檔，{len(groups)} 群",
             "path": str(out)}]
```

> 不直接刪檔，只輸出清單；後續 user 可手動 / 配合 rename_plan 風格的 `delete_plan.csv`（未來功能）。

---

### B 組驗收清單

- [ ] `tests/test_engineering_*.py` 對 C1–C5 各補 1 個 happy + 1 個錯誤情境（缺工具 / 欄位不存在）。
- [ ] C1/C3 需在 `pyproject.toml` 加 optional extra：

```toml
[project.optional-dependencies]
ocr = ["rapidocr-onnxruntime>=1.3", "PyMuPDF>=1.24"]
```

- [ ] 在 `docs/` 補一份 `engineering_external_tools.md`，列 ODA File Converter / ocrmypdf 安裝指引。

---

## 區塊 D — 架構延伸

> 此區為較大重構，建議拆 PR：D1 → D2 → D3，每個獨立可合併。

### D1. Workflow 串接（workflow.json）

**目標**：把多條 action 串成一個可重複執行的工作流，例如：

```jsonc
{
  "id": "workflow.iso_intake",
  "title": "ISO 收件 SOP",
  "category": "工作流",
  "steps": [
    {"action": "pdf.split_pages"},
    {"action": "engineering.ocr_pdf_to_text"},
    {"action": "iso.pdf_page_naming"}
  ]
}
```

**檔案異動**：

- `launcher/core/workflow_model.py`：`@dataclass Workflow { id, title, steps: list[WorkflowStep] }`，`WorkflowStep { action_id, options }`。
- `launcher/core/workflow_runner.py`：依序呼叫 `ActionRunner.run`，每步把上一步輸出的 `artifact.path` append 進下一步 context.files（或 options，視 step 設定）。
- `launcher/core/registry.py`：在 plugin folder 讀完 actions 後，額外掃 `workflows/*.json`（全域），把每個 workflow 視為虛擬 ActionDefinition（`command.type = "workflow"`，runner 端 dispatch）。
- `launcher/ui/`：新增 `workflow_builder.py` 對話框，可拖拉 action 排序、編輯 options。
- 儲存：`%LOCALAPPDATA%/EngineeringLauncher/workflows/*.json`。

**最小可行版本**：先支援線性 steps（無條件分支、無失敗重試），上下步只透過 `last_artifact_paths` 傳遞。

**驗收**：`test_workflow_runner.py` 跑「split_pages → bucket_by_ext」雙步流程，驗證 artifact 確實被 carry over。

---

### D2. 動作歷史與一鍵還原

**目標**：對 high-risk action（rename / bucket / merge / rotate）寫一筆 reversible record，UI 提供「還原此動作」按鈕。

**檔案異動**：

- `launcher/core/history.py`：新增 `HistoryEntry { id, action_id, started_at, undo_plan }`；`undo_plan` 為 `[{"op": "rename", "src": ..., "dst": ...}, ...]` 之類的反向操作清單。
- High-risk worker 結束時，把 undo_plan 透過 event `{"type": "history", "undo_plan": [...]}` 回傳；ActionRunner 攔截寫入 `~/.engineering_launcher/history/<job_id>.json`。
- `launcher/ui/job_monitor.py`：新增「還原」按鈕，呼叫 `HistoryService.undo(job_id)`。
- 第一版只實作 rename / bucket 的 undo（皆為 move 反向）；merge/rotate 因為產生新檔，undo = 刪除新檔（需二次確認）。

**驗收**：`test_history.py` 跑 bucket → undo，檔案回到原位。

---

### D3. LLM 輔助 rename plan

**目標**：使用者用自然語言描述命名規則，由 Anthropic API（或 OpenAI / 本機 LLM 介面）產生 `rename_plan.csv` 草稿。

**檔案異動**：

- `launcher/plugins/llm/llm_rename.py`：

```python
def llm_generate_rename_plan(payload):
    instruction = payload["options"]["instruction"]      # 使用者輸入
    target = folder(payload)
    names = [p.name for p in sorted(target.iterdir()) if p.is_file()]
    from launcher.plugins.llm.client import chat_complete
    suggestion = chat_complete(
        system="你是檔名標準化助手。輸出 CSV：src,dst，第二欄是建議新檔名；不要加註釋。",
        user=f"規則：{instruction}\n\n檔名清單：\n" + "\n".join(names),
    )
    plan = target / "rename_plan.csv"
    plan.write_text("src,dst,apply\n" + _normalize_llm_csv(suggestion), encoding="utf-8-sig")
    return [{"type": "artifact", "message": "已產生 LLM rename_plan.csv（請人工 review）",
             "path": str(plan)}]
```

- `launcher/plugins/llm/client.py`：包一層 `chat_complete(system, user)`，從 `state.json["llm"] = {"provider": "anthropic"|"openai", "api_key": ..., "model": ...}` 讀取。**禁止把 api_key 寫死在 code 或 commit 進 repo。**
- `launcher/ui/preferences_dialog.py`：新增 LLM 分頁，輸入 provider / key / model；key 以 Windows DPAPI 加密（`pywin32` 已有依賴）。
- 安全注意：產出檔名以後一律寫進 plan 給人工確認，不直接 apply。

**actions.json**（plugin `llm`）：

```jsonc
{
  "id": "llm.rename_plan",
  "title": "LLM 產生更名計畫",
  "category": "更名",
  "description": "用自然語言敘述命名規則，由 LLM 產生 rename_plan.csv 草稿。",
  "accepts": {"requires_folder": true},
  "risk": "high",
  "command": {"type": "python_module",
              "module": "launcher.plugins.llm.llm_rename",
              "entry": "llm_generate_rename_plan"}
}
```

**驗收**：`test_llm_rename.py` mock `chat_complete` 回固定字串，驗證 plan 內容與寫入位置；不發真 API。

---

## 收尾 — 整體完成定義 (Definition of Done)

- [ ] `pytest -q` 全綠（含本指令書新增的測試）。
- [ ] `python -m launcher.app.self_test` 或 `.\run_self_test.ps1` 通過。
- [ ] `launcher.core.registry.ActionRegistry.load()` 在啟動時，`RegistryLoadReport.issues` 為空。
- [ ] 對話框類 UI 改動需在 `tests/` 內補 widget-less 邏輯測試（仿 `palette_search`、`edge_positioner` 的純函式拆法）。
- [ ] 文件更新：
  - [ ] `README.md`「Phase 1 Status / Planned next」段同步移除已完成、新增實作中項目。
  - [ ] 在 `docs/` 補 `engineering_external_tools.md`、`workflows_guide.md`（D1 完成後）。
- [ ] `pyproject.toml` optional-dependencies 補 `ocr`、`llm` 兩組 extras；CI / install 文件提示「不裝亦可，相關 action 啟動時會 raise 並提示」。

---

## 附錄 A — 新建檔案清單（給 Codex 對齊用）

```
launcher/plugins/_common/__init__.py
launcher/plugins/_common/payload_utils.py
launcher/plugins/file_ops/__init__.py
launcher/plugins/file_ops/plugin.json
launcher/plugins/file_ops/actions.json
launcher/plugins/file_ops/regex_rename.py
launcher/plugins/file_ops/batch_label.py
launcher/plugins/file_ops/bucket.py
launcher/plugins/file_ops/tree.py
launcher/plugins/file_ops/hash_clipboard.py
launcher/plugins/file_ops/folder_stats.py
launcher/plugins/engineering/__init__.py
launcher/plugins/engineering/plugin.json
launcher/plugins/engineering/actions.json
launcher/plugins/engineering/dwg.py
launcher/plugins/engineering/iso_compare.py
launcher/plugins/engineering/ocr_pdf.py
launcher/plugins/engineering/folder_diff.py
launcher/plugins/engineering/duplicates.py
launcher/plugins/llm/__init__.py
launcher/plugins/llm/plugin.json
launcher/plugins/llm/actions.json
launcher/plugins/llm/client.py
launcher/plugins/llm/llm_rename.py
launcher/core/workflow_model.py
launcher/core/workflow_runner.py
launcher/core/history.py
launcher/ui/pdf_merge_dialog.py
launcher/ui/copy_options_dialog.py
launcher/ui/workflow_builder.py
docs/engineering_external_tools.md
docs/workflows_guide.md
tests/test_file_ops_regex_rename.py
tests/test_file_ops_batch_label.py
tests/test_file_ops_bucket.py
tests/test_file_ops_tree.py
tests/test_file_ops_hash.py
tests/test_file_ops_stats.py
tests/test_pdf_merge.py
tests/test_pdf_rotate.py
tests/test_engineering_iso_compare.py
tests/test_engineering_folder_diff.py
tests/test_engineering_duplicates.py
tests/test_engineering_dwg.py
tests/test_workflow_runner.py
tests/test_history.py
tests/test_llm_rename.py
```

## 附錄 B — 修改檔案清單

```
launcher/core/registry.py             # visible_actions / workflow 掛載
launcher/core/state_store.py          # developer_mode / oda_path / llm 設定
launcher/ui/command_palette.py        # visible_actions / copy options dialog 攔截
launcher/ui/dock_window.py            # visible_actions
launcher/ui/preferences_dialog.py     # developer_mode、ODA path、LLM 設定
launcher/ui/job_monitor.py            # 還原按鈕（D2）
launcher/plugins/copy_utils/actions.json   # 新指令、刪舊指令
launcher/plugins/copy_utils/copy_paths.py  # 新 entry + 舊 entry 保留
launcher/plugins/system_tools/actions.json # 移除 reveal_first_file
launcher/plugins/system_tools/system_actions.py # open_folder_or_reveal
launcher/plugins/pdf_tools/actions.json    # 新增 merge / rotate
launcher/plugins/pdf_tools/pdf_actions.py  # 新增 merge_pdfs / rotate_pdfs
pyproject.toml                        # optional-dependencies: ocr / llm
README.md                             # 同步狀態
```

---

## 附錄 C — 對 Codex 的執行順序建議

1. **Phase 1（半天）**：A1 + A2 + A3（清理 + copy 重構 + reveal 合併）。風險低、impact 高、立刻能看到效果。
2. **Phase 2（1 天）**：B1–B9（高頻新指令 + file_ops plugin）。新增 plugin，建立 `_common` 基礎建設。
3. **Phase 3（1–2 天）**：C1–C5（工程專用）。引入 optional dependencies、外部工具偵測樣板。
4. **Phase 4（2–3 天）**：D1（workflow）→ D2（history）→ D3（LLM）。架構級重構，最後做。

每個 Phase 結束都應跑一次完整 `pytest`、`run_self_test.ps1`，並更新 `README.md` 的 Phase 1 Status 區塊。

---

> 完。如執行中有歧義，預設行為一律參照「**先產 plan 檔 → 人工 review → 套用**」原則。
