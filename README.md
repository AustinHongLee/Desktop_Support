# Engineering Launcher

Lightweight Windows engineering launcher / floating automation dock.

The launcher is intentionally small:

- resident PyQt6 UI
- JSON-driven action registry
- demand-driven context detection
- out-of-process workers for heavy tools
- plugin folders for future DWG, PDF, Weld, Navisworks, Git, and AI workflows

## Start

一般使用者建議雙擊根目錄的 `START.cmd`。它會啟動工具列；如果啟動失敗，視窗會停住並顯示 `launcher_startup.log`。

`START.vbs` 仍保留為靜默背景啟動入口，但不建議拿來除錯；它若失敗只會寫入 `%LOCALAPPDATA%\EngineeringLauncher\logs\launcher_startup.log`。

啟動問題請雙擊 `START_DEBUG.cmd`，它會用前景模式啟動並保留錯誤輸出。

右鍵登錄管理請雙擊根目錄的 `RIGHT_CLICK_MANAGER.vbs`。它會開啟管理視窗，讓不熟 regedit 的使用者直接安裝、修復或移除 Explorer 右鍵入口。

進階/除錯入口已集中放在 `scripts\launcher\`：

- `scripts\launcher\run_launcher.ps1`：背景啟動
- `scripts\launcher\run_launcher.ps1 -ShowDock`：背景啟動並顯示工具列
- `scripts\launcher\run_launcher_debug.ps1 -Restart`：重啟並追蹤 ISO 工作台 log
- `scripts\launcher\run_self_test.ps1`：無 UI 自測

## Explorer Right-Click Context

Install the per-user Explorer context menu:

```powershell
.\scripts\install_explorer_context_menu.ps1
```

After installation, right-click a file, folder, folder background, or drive and choose
`送到工程工具列`. The launcher will use that explicit Explorer target as the current context.

Remove it with:

```powershell
.\scripts\uninstall_explorer_context_menu.ps1
```

If `PyQt6` is not installed yet, the app automatically starts a built-in Tk test
launcher so the core workflow is still usable.

For a no-GUI smoke test:

```powershell
.\scripts\launcher\run_self_test.ps1
```

Optional OCR support for ISO PDF serial detection:

```powershell
.\scripts\install_ocr.ps1
```

The ISO naming workbench lazy-loads RapidOCR only when image serial detection runs.
If OCR is unavailable, it falls back to the lightweight OpenCV detector.

Use `Ctrl+K` while the dock is focused to open the command palette. Drop files onto the
dock to make those files the active context.

## First Architecture Boundary

The permanent launcher process owns UI, action discovery, context collection, and job dispatch.
Tool logic runs in short-lived worker processes so heavy modules are loaded only when needed.

```text
PyQt6 dock / tray / command palette
  -> ActionRegistry
    -> ContextService
    -> ActionRunner
      -> launcher.workers.worker_host
        -> plugin implementation
```

## Plugin Shape

```text
launcher/plugins/<plugin_id>/
  plugin.json
  actions.json
  <tool implementation>.py
```

`actions.json` describes what the launcher can show. Worker modules do the real work.

## Phase 1 Status

Implemented:

- floating dock shell
- tray menu
- command palette
- drag/drop file context
- active/topmost Explorer context via pywin32
- edge-snapped single-row toolbar with monitor selection
- horizontal toolbar on top/bottom and vertical toolbar on left/right
- explicit context source menu: topmost Explorer, specific Explorer window, manual folder, manual files, development CWD
- recent commands, recent files, and recent folders
- no-dependency Tk fallback test launcher
- JSON plugin and action registry
- out-of-process Python worker host
- copy path / copy filename / copy current folder actions
- filename list clipboard actions:
  - selected names
  - selected basenames
  - current folder item names
  - current folder file names
  - current folder file basenames
- common Windows workflow actions: Explorer, PowerShell, VS Code, reveal file, open selected files, file list TXT
- rename workflows:
  - rename selected file from clipboard text
  - create `rename_plan.csv`
  - apply `rename_plan.csv` rows marked `YES`
- PDF workflows:
  - split selected PDFs into page-numbered single-page PDFs
- ISO workflows:
  - single ISO PDF naming workbench UI
  - choose combine PDF or existing page PDF folder
  - split combine PDF into page PDFs
  - load ISO list from `.xlsx`, `.xlsm`, or `.csv`
  - map `sort/流水號` to `管線號碼`
  - generate names with `{serial}--{line}.pdf`
  - review and apply PDF page renames in the same table UI
  - optional RapidOCR + OpenCV serial-number detection with a draggable detection region
- diagnostics action for worker smoke tests

Planned next:

- active Explorer window context provider
- global hotkey
- job log persistence
- PDF merge plugin
- packaged Windows executable
