# Shutdown Safety 嫌疑確認筆記

> 建立日期：2026-06-08  
> 目的：保留本次重災後對 `桌面輔助系統` 的初步嫌疑分析，供後續另開修補專案使用。  
> 原則：目前不能定罪，只記錄已確認事實、可重現風險、後續建議。

## 1. 背景

使用者近期曾遇到 Windows profile / 登入 / 自動修復相關問題，後續又發生更嚴重的 Windows 問題，最後只能重灌。

使用者懷疑本專案的「關機前安全檢查 / 強制停止程序」功能可能有反效果：

- 原本設計目標：關機前檢查是否有本專案相關程序、job、lock、temp 或 file dependency blocker。
- 若存在可安全停止的程序，提供等待、正常停止、強制停止或取消關閉。
- 使用者懷疑：這個功能本身可能在關機或 Windows session end 階段卡住，或誤判程序後造成不必要的停止。

## 2. 本次只讀檢查結果

目前不能說本專案是 Windows 重災主因。

本次檢查到：

- 目前沒有 `桌面輔助系統` 的 launcher / worker 常駐程序。
- `.runtime\running` 目前是空的。
- `shutdown_safety_inspector --dry-run --print-json` 掃描結果為 `blocker_count = 0`。
- 新系統目前沒有看到本專案相關的 Application Hang / Application Error。
- 沒看到本專案被放進 Windows 開機啟動項或工作排程。
- focused tests 通過：

```text
py -3.12 -m pytest tests/test_shutdown_safety.py tests/test_shutdown_safety_dialog.py -q
12 passed
```

## 3. 不能下的結論

目前沒有足夠證據可以說：

- 本專案造成 Windows profile 損壞。
- 本專案造成 Windows 自動修復失敗。
- 本專案造成 SSD / NTFS / Windows Update 災情。
- 本專案是這次重灌的直接主兇。

因為舊系統已重灌，原始 Event Viewer、User Profile Service、Windows Update、SrtTrail、CBS/DISM、minidump 等證據很可能已不存在或不完整。

## 4. 仍然值得處理的實際風險

### 4.1 PID reuse 誤判風險

位置：

- `launcher/core/shutdown_safety.py`
- `_metadata_for_process(...)`
- `scan_shutdown_blockers(...)`
- `apply_shutdown_policy(...)`

目前邏輯會用 job metadata 裡的 `pid` 對目前程序：

```python
def _metadata_for_process(pid: int, lock: RuntimeProcessLock | None, jobs: dict[str, JobMetadata]) -> JobMetadata | None:
    if lock is not None and lock.job_id in jobs:
        return jobs[lock.job_id]
    for metadata in jobs.values():
        if metadata.pid == pid:
            return metadata
    return None
```

問題：

- Windows PID 會重用。
- 舊 job metadata 可能長期留在 `.runtime\jobs`。
- 若某個新程序剛好取得舊 PID，而且 command line 含專案 root，可能被套用舊 job 的 `safe_to_kill`。
- 如果舊 metadata 標示 `safe_to_kill = "Safe"`，該程序可能被判定為可自動停止。

本次用臨時目錄做過最小重現：

1. 建立舊 job metadata，PID 設為 `12345`，`safe_to_kill = "Safe"`。
2. 不建立 active lock。
3. 建立目前 process snapshot，PID 同樣為 `12345`，process name 為 `pwsh.exe`，command line 含 project root。
4. `scan_shutdown_blockers(...)` 會產生 blocker。
5. 該 blocker 被標示：
   - `safe_to_kill = "Safe"`
   - `can_automatically_stop = true`
   - `command_line_contains_project_root = true`

這代表設計上存在可重現的誤判漏洞。

### 4.2 Windows shutdown event 中同步掃描與 kill

位置：

- `launcher/ui/dock_window.py`
- `nativeEvent(...)`
- `_handle_windows_shutdown_event(...)`

目前流程：

```python
def nativeEvent(self, event_type, message):
    if sys.platform == "win32":
        message_id = _windows_message_id(message)
        if message_id == WM_QUERYENDSESSION:
            self._handle_windows_shutdown_event("WM_QUERYENDSESSION")
            return True, 1
        if message_id == WM_ENDSESSION:
            self._handle_windows_shutdown_event("WM_ENDSESSION")
            return True, 0
    return False, 0
```

```python
def _handle_windows_shutdown_event(self, reason: str) -> None:
    report = scan_shutdown_blockers(scan_reason=f"windows.{reason.lower()}")
    write_report(report)
    apply_shutdown_policy(report, kill_safe=True)
```

風險：

- Windows 正在結束 session 時，同步做 process scan、寫 report、套用 `kill_safe`。
- 掃描目前會透過 PowerShell / WMI 查 Win32_Process，最多可能等待數秒。
- `taskkill.exe` 每個 PID timeout 最高 15 秒。
- 若多個 blocker 或 WMI 異常，可能拖慢關機流程。
- 在 `WM_QUERYENDSESSION / WM_ENDSESSION` 中做這些事太重，容易造成「程式正在阻止關機」或使用者感覺 Windows 卡住。

### 4.3 Tauri 版 close 行為容易造成常駐誤解

位置：

- `frontend/tauri-spike/src-tauri/src/main.rs`
- `frontend/tauri-spike/src/App.tsx`

觀察：

- Tauri 視窗 close 被 prevent，實際行為是 hide 到 system tray。
- tray 的「離開」才會真正 `app.exit(0)`。

這不太像會造成 Windows 重災，但可能造成：

- 使用者以為程式關了，其實還常駐。
- 後台仍可能被使用者誤認為「關不乾淨」。
- 若未來加上 shutdown safety 或 background scan，這種常駐模式會提高排查難度。

## 5. 後續修補建議

建議另開修補工作，優先做以下事項。

### A. 修 PID reuse 誤判

建議規則：

- 只有 active `.runtime\running\*.json` lock 能把 metadata 套到目前 process。
- 不要只靠舊 `.runtime\jobs\*.json` 的 PID 連結目前 process。
- 若沒有 active lock：
  - 可用 command line 判斷「可能屬於本專案」。
  - 但不可套用舊 metadata 的 `safe_to_kill`。
  - 預設至少應為 `Unknown` 或 `Caution`。
  - 不可 `can_automatically_stop = true`。

建議修改方向：

```python
def _metadata_for_process(pid, lock, jobs):
    if lock is not None and lock.job_id in jobs:
        return jobs[lock.job_id]
    return None
```

若仍想保留 job fallback，至少要額外驗證：

- metadata.status 必須是 `running`。
- metadata.started_at 與 process.started_at 接近。
- metadata.command_summary 與 process.command_line 有足夠相似度。
- metadata.pid > 0。
- metadata 不能太舊。

### B. Windows shutdown event 改為保守模式

建議：

- `WM_QUERYENDSESSION / WM_ENDSESSION` 中只做極輕量動作。
- 可以寫一筆簡短 log，但不要 WMI 掃全系統。
- 不要在 Windows shutdown event 中自動 `kill_safe`。
- 若需要清理，應在使用者主動按「結束工程工具列」時做。

建議策略：

- App 主動關閉：可顯示 dialog，可讓使用者套用 Safe。
- Windows 關機事件：只記錄「Windows 正在結束 session」，然後快速放行。
- 背景掃描或 shutdown cockpit 可以由使用者平時手動開，不要卡在系統關機流程。

### C. Tauri close 行為變得更透明

建議：

- 第一次按 X 時顯示提示：「已隱藏到系統匣，未結束」。
- tray menu 提供明確「離開」與「關機安全檢查」。
- Cockpit 頁面顯示目前是否常駐。

### D. Runtime metadata 維護

建議：

- `.runtime\jobs` 舊資料可保留作診斷，但掃描時不可全部信任。
- 新增 read-only prune report 或 archive 機制。
- 不要自動刪除舊 runtime，除非使用者明確確認。
- 可新增「匯出 runtime 診斷包」功能。

## 6. 建議新增測試

### test_pid_reuse_without_active_lock_is_not_safe

測試目的：

- 舊 job metadata 有 `pid` 與 `safe_to_kill = Safe`。
- 目前 process snapshot PID 相同，command line 含 project root。
- 但沒有 active lock。
- 預期不可套用舊 metadata。
- 預期不可自動停止。

### test_windows_shutdown_event_does_not_auto_kill

測試目的：

- 模擬 `WM_QUERYENDSESSION` 或 `_handle_windows_shutdown_event(...)`。
- 確認不呼叫 `apply_shutdown_policy(..., kill_safe=True)`。
- 或改成只寫 report / log。

### test_tauri_close_is_hide_not_exit_documented

測試目的：

- 確認 close request 是 hide。
- 文件或 UI 明確告知使用者程式仍在 tray。

## 7. 後續處理優先級

建議優先順序：

1. 修 PID reuse 誤判。
2. Windows shutdown event 中取消自動 kill。
3. 補測試。
4. 增加 UI 文案，讓 Tauri tray 常駐行為更透明。
5. 最後才處理 runtime 舊紀錄整理。

## 8. 給後續工作用的一句話

目前不能證明 `桌面輔助系統` 是 Windows 重災主兇；但 shutdown safety 有一個可重現的 PID reuse 誤判漏洞，而且 Windows shutdown event 裡同步掃描與自動 kill 的設計偏重，建議先保守修掉，避免它在關機流程中成為新的不確定因素。

## 9. 2026-06-08 修補紀錄

本輪已先完成保守安全修補：

- `launcher/core/shutdown_safety.py`：`_metadata_for_process(...)` 不再用舊 `.runtime\jobs` 的 PID fallback 套 metadata；沒有 active `.runtime\running` lock 時，即使命中舊 PID，也不可取得舊 job 的 `safe_to_kill = Safe`。
- `launcher/ui/dock_window.py`：Windows `WM_QUERYENDSESSION` / `WM_ENDSESSION` 改為只寫輕量 marker/report 後快速放行；不再同步 `scan_shutdown_blockers(...)`，也不再 `apply_shutdown_policy(..., kill_safe=True)`。
- `tests/test_shutdown_safety.py`：新增 `test_pid_reuse_without_active_lock_is_not_safe`，鎖住 PID reuse 不能自動停止。
- `tests/test_dock_window.py`：更新 Windows shutdown event 測試，確認不掃描、不開 dialog、不自動 kill。
- `scripts/test.ps1`：新增單一測試入口；Shutdown Safety focused tests 可用 `.\scripts\test.ps1 -Suite shutdown`。
- `scripts/tauri/run_dev_app.ps1`：Tauri dev/test UI 先檢查原生工具鏈；缺 Rust/MSVC `link.exe`/Windows SDK `rc.exe` 時退到 browser fallback，讓 PyQt-to-Tauri 搬遷中的 React UI 仍可測。
- `scripts/dev/prepare_dev_environment.ps1`：新增開發環境檢查/安裝入口；預設只檢查，`-InstallMissing` 才嘗試補 Rustup、Visual Studio C++ workload、MSVC、Windows SDK。
- `tests/test_smoke.py`：新增入口 smoke tests，確認根目錄只剩 `START_HERE.cmd`、選單文字與 choice code 一致、dev-env JSON 可解析、dock shutdown message helper 可 import。
- `frontend/tauri-spike/src-tauri/src/main.rs`：Tauri tray 的「離開」不再直接 `app.exit(0)`；會先跑 shutdown safety scan，只有無 blockers 才退出，有 blockers 或 scan 失敗時開 Shutdown cockpit。
- `frontend/tauri-spike/src/App.tsx`：支援 Tauri tray 發出的 shutdown cockpit / refresh event，讓安全檢查被擋下時切到正確頁面。
- `frontend/tauri-spike/src-tauri/src/main.rs`：Tauri 視窗 close=hide 第一次會顯示常駐 tray 提示，並以 `.runtime\flags\hide-to-tray-notified` 記錄不重複打擾。

仍可後續處理：

- Tauri close/tray 常駐提示可再做更明顯的 UI 提醒。
- 真正原生 Tauri tray/window/sidecar 驗證需要完整 Visual Studio Build Tools C++/MSVC/Windows SDK；目前未包 exe 前可先用 browser fallback 測 UI。
- `.runtime\jobs` 舊紀錄整理可做 read-only report 或手動 archive，不建議自動刪除。
