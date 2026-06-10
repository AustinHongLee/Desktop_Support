# System Residency Foundation

> Date: 2026-06-08  
> Scope: 基礎規則，用於後續把 Desktop Support 打包成 exe 並變成使用者層級常駐程式。  
> Principle: 常駐不等於系統服務；先穩定、可回復、可診斷，再談更高權限。

## 1. 根目錄規則

本專案從現在起分成兩種 root：

- code root：程式碼、外掛、開發期 `.venv` 所在位置。Python 端是 `launcher.core.paths.project_root()`。
- runtime root：使用者狀態、`.runtime`、job、lock、log、report 所在位置。Python 端是 `launcher.core.paths.runtime_root()`。

解析順序：

1. `DESKTOP_SUPPORT_PROJECT_ROOT`：相容舊流程，也可指定要診斷的 runtime root。
2. source checkout：開發期仍使用 repo root，讓既有 `.runtime` 與測試流程可延續。
3. `%LOCALAPPDATA%\EngineeringLauncher`：打包 exe / 非 source checkout 的預設 runtime root。

狀態檔規則：

- `DESKTOP_SUPPORT_STATE_PATH` 可覆寫單一 state file。
- `DESKTOP_SUPPORT_DATA_ROOT` 可覆寫 per-user app data root。
- 預設 state path 是 `%LOCALAPPDATA%\EngineeringLauncher\state.json`。

## 2. 常駐邊界

Desktop Support 應先維持使用者層級常駐，不升級成 Windows service：

- 不寫 HKLM 作為預設安裝路徑。
- 不需要系統管理員權限即可啟動、退出、讀寫自己的 runtime。
- 不攔截 Windows shutdown，不做同步重掃或 kill。
- 所有危險動作維持使用者明確確認。

Single instance mutex 使用 runtime root identity，不使用 PyInstaller 解壓路徑或 exe 暫存路徑，避免 packaged exe 每次啟動產生不同 mutex。

## 3. Shutdown Safety 規則

Shutdown Safety 只處理可驗證的本專案程序：

- active `.runtime\running` lock 才能把 job metadata 套到目前 PID。
- 舊 `.runtime\jobs` 的 PID 不可單獨證明目前程序身分，避免 PID reuse。
- 沒有 active lock 時，即使命令列含 runtime root，也只能視為 Unknown/Caution，不可自動 stop。
- Windows `WM_QUERYENDSESSION` / `WM_ENDSESSION` 只寫輕量 marker/report 後快速放行。
- 手動 app quit 可以顯示 dialog；Windows session end 不開 dialog、不掃 WMI、不 `kill_safe`。
- Tauri tray quit 也不可繞過 shutdown safety；正常使用者退出先 scan，無 blockers 才離開，有 blockers 或 scan 失敗就打開 Shutdown cockpit。
- Tauri close=hide 需要首次提示，避免使用者以為按 X 已經結束程式；提示狀態可寫在 runtime root 的輕量 flag。

## 4. Worker 啟動規則

Worker 需要同時滿足 import 相容性與 runtime 可診斷性：

- `cwd` 使用 code root，確保 source checkout 與開發外掛可 import。
- command line 與 `DESKTOP_SUPPORT_PROJECT_ROOT` 使用 runtime root，讓 shutdown safety、job lock、report 指向同一個資料根。
- worker metadata 必須透過 `ProcessGuard` 寫 lock/job；未寫 lock 的程序不可取得 Safe 身分。

## 5. 入口規則

給人的入口只保留根目錄一個主路：

- `START_HERE.cmd`

`START_HERE.cmd` 內提供一般啟動、debug、右鍵管理、unit 測試、Tauri dev/test UI、開發環境檢查。Tauri dev/test UI 是 PyQt-to-Tauri 搬遷用入口；本機沒有 MSVC/Windows SDK 時可以退到 browser fallback 測 React UI，但不能宣稱原生 Tauri tray/window/sidecar 已驗證。Tauri release build 仍屬進階打包流程，不放在主入口。

開發環境檢查集中在 `scripts\dev\prepare_dev_environment.ps1`；預設只檢查，只有加 `-InstallMissing` 才會嘗試安裝 Rustup / Visual Studio C++ workload / Windows SDK。

入口 smoke checks 集中在 `.\scripts\test.ps1 -Suite smoke`，用來鎖住根目錄唯一入口、`START_HERE.cmd` 選單、dev-env JSON、Tauri fallback 腳本與 dock window import chain。

其餘 `.cmd` / `.vbs` / `.ps1` 可以保留作相容或內部工具，但 README 要明確標示，不讓使用者把每個腳本都當成同等入口。

## 6. 後續打包注意

Tauri / packaged exe 仍有舊版 Python workbench 相容層。未來完整打包前要再確認：

- legacy PyQt workbench 是否仍需 source checkout / local Python。
- ISO workflow 是否要改成 sidecar API，而不是依賴開發期 `.venv`。
- Explorer 右鍵入口未來應指向正式 exe；目前仍是 source checkout + `pythonw.exe` 模式。
- 原生 Tauri build 需要 Rust、Visual Studio Build Tools C++/MSVC `link.exe`、Windows SDK `rc.exe`；未安裝前只能做 browser UI 測試。
- 自動更新、開機啟動、crash recovery 都只能寫入 per-user location，不能默默升權。
