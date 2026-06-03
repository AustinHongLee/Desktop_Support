# Engineering Launcher

Lightweight Windows engineering launcher / floating automation dock.

The launcher is intentionally small:

- resident PyQt6 UI
- JSON-driven action registry
- demand-driven context detection
- out-of-process workers for heavy tools
- plugin folders for future DWG, PDF, Weld, Navisworks, Git, and AI workflows

## Start

一般使用者建議雙擊根目錄的 `START.vbs`。它會直接啟動 Tauri 桌面版，不會掛著 cmd 視窗；工具列可從系統匣圖示叫回來。

`START.cmd` 只是一個薄啟動器：已建置 Tauri exe 時會轉交給 `START.vbs` 並立刻退出；找不到 exe 時才停下來提示 build 指令。

啟動問題請雙擊 `START_DEBUG.cmd`，它會用前景模式啟動並保留錯誤輸出。

右鍵登錄管理請雙擊根目錄的 `RIGHT_CLICK_MANAGER.vbs`。它會開啟管理視窗，讓不熟 regedit 的使用者直接安裝、修復或移除 Explorer 右鍵入口。

進階/除錯入口已集中放在 `scripts\launcher\`：

- `scripts\launcher\run_launcher.ps1`：背景啟動
- `scripts\launcher\run_launcher.ps1 -ShowDock`：背景啟動並顯示工具列
- `scripts\launcher\run_launcher_debug.ps1 -Restart`：重啟 debug launcher；log tail 預設關閉
- `scripts\launcher\run_launcher_debug.ps1 -Restart -Tail`：重啟並明確追蹤 ISO 工作台 log
- `scripts\launcher\run_self_test.ps1`：無 UI 自測

Tauri / React 桌面版目前是主要桌面入口。它啟動時走桌面 dock 小尾巴，點開後才展開未來感 cockpit：

```powershell
.\scripts\tauri\build_desktop_app.ps1 -Configuration Release
.\frontend\tauri-spike\src-tauri\target\release\desktop-support-tauri-spike.exe
```

這個 build 會同時用 PyInstaller 打包 `desktop-support-backend.exe`，並放在 Tauri exe 同資料夾。Tauri 會優先呼叫 sidecar；開發環境找不到 sidecar 時才 fallback 到本機 Python。若要掃描既有專案 runtime，請保留專案資料夾，或用 `DESKTOP_SUPPORT_PROJECT_ROOT` 指向要檢查的 runtime root。

Tauri 桌面版會常駐系統匣。關閉視窗會隱藏到系統匣，不會結束程式；左鍵點 tray 圖示可叫回 dock，右鍵選單可顯示 dock、開 Cockpit、隱藏或離開。

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

## Shutdown Safety Inspector

Shutdown Safety Inspector 是關閉保護 UI：使用者要關閉 app，或 Windows 送出 `WM_QUERYENDSESSION` / `WM_ENDSESSION` 時，它會先掃描本專案 runtime，列出誰還握著 process、job、lock、temp/output/log 或檔案關係。

它的目標是降低 orphan process、file handle、temp lock 造成使用者登出時 profile/hive 無法卸載的風險。它不能修復 Windows profile、User Profile Service 1512/1517、`ProfileList` 或 registry hive；也不修改 Windows Registry、不刪 profile、不關 Explorer/GIMP/Windows service/非本專案程序。

Runtime schema:

```text
.runtime/
  running/*.json          active process lock
  jobs/*.json             job metadata / status
  logs/safety.log         safety events
  logs/shutdown_safety_report_*.json
  relationships/*.json    file relationship / dependency graph edges
  temp/*                  job temp folders
```

每個 job metadata 包含 `job_id`、`component`、`process_role`、`pid`、`parent_pid`、`command_summary`、`input_files`、`output_files`、`temp_dirs`、`started_at`、`safe_to_kill`、`kill_consequence`、`cleanup_strategy`。`ActionRunner` 會透過 `ProcessGuard` 啟動 worker，記錄 process lock、job metadata、stdout/stderr/stdin pipe 清理策略，並在完成、失敗或中斷後更新狀態與移除 stale lock。

UI flow:

1. 掃描本專案 process：只列出 command line 含 project root，或 `.runtime\running` 中仍 active 的 PID。
2. 合併 `.runtime\jobs`、`.runtime\temp`、`.runtime\relationships`，顯示 PID、ProcessName、Parent PID、CommandLine 摘要、啟動時間、job id、lock/temp/output/log、dependency graph、判斷原因與 child process tree。
3. 標示「他是誰」：App 主程序、Worker process、ffmpeg encoder、Python model runner、File watcher、Background downloader、Unknown but project-owned。
4. 標示 SafeToKill：
   - `Safe`：可正常停止，最多重跑工作。
   - `Caution`：可關，但輸出檔可能不完整、cache/temp 可能要重建、job 可能要 rollback。
   - `Dangerous`：預設不自動關，可能正在寫重要檔案或資料庫。
   - `Unknown`：資訊不足，只列出不自動處理。
5. 使用者可選 Wait、Graceful stop、Force stop、Open log、Open related folder、Inspect dependency graph、Ignore once、Cancel shutdown / close。

自動策略：`Safe` 可預設 graceful stop；`Caution` 需要確認才 force stop；`Dangerous` / `Unknown` 預設不殺。Windows shutdown event 的時間通常很短，因此事件中只快速寫入 JSON report、嘗試停止 Safe blocker，然後放行，不永久阻止 Windows 關機。停止程序一律不用 `shell=True`；`taskkill.exe` 只用參數陣列，且拒絕停止 command line 不含本專案路徑的 PID。

手動檢查：

```powershell
.\scripts\shutdown_safety_inspector.ps1
.\scripts\shutdown_safety_inspector.ps1 -DryRun
.\scripts\shutdown_safety_inspector.ps1 -KillSafe
.\scripts\shutdown_safety_inspector.ps1 -KillAllProjectOwned
.\scripts\shutdown_safety_inspector.ps1 -DryRun -MockShutdownEvent
```

app 內可從「更多」或指令面板開啟 `Shutdown Safety Inspector`。Windows shutdown event 已由 PyQt native event handler 接入 `WM_QUERYENDSESSION` / `WM_ENDSESSION`；這是保護性檢查與清理，不做真正關機測試。

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
