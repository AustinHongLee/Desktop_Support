# ISO PDF 拆頁命名 — 三方先導統整與執行路線

> Date: 2026-06-08  
> Inputs: DeepSeek `iso_pdf_workbench_blueprint_v0.2.md`, Claude Opus `iso_pdf_workbench_pilot_plan_v0.1.md`, Qwen `iso_pdf_next_stage_design_2026-06-08.md`  
> Verdict: 先補「失敗可還原」地基，再動工作台與調校；一鍵正常路線暫時只做保護，不做大拆。

---

## 0. 總裁決

三份文件的共識很明確：

- 一鍵已趨穩定，給長官與同事使用，不能塞進 ROI、欄位、threshold、raw log、legacy bridge。
- 工作台是「修問題列、看證據、重新產生、套用」的地方。
- 調校是「修根因」的地方，包含 ROI、Profile、Pilot List、Run Log、Debug Bundle、Replay。
- PyQt6 目前仍是 legacy / 對照 / 測試線，不拔、不藏到完全不能用。
- 後端判斷邏輯仍以 Python 為單一真相源，React 不重刻 `_row_status`、ISO 對應、OCR 校正、rename validation。

真正需要裁決的是優先順序。

**本統整版決定：P0 不先大拆 App.tsx。P0 先做 Run Log / Failure Handoff / Debug Bundle / Profile draft-published。**

理由：

- 一鍵正常路線已經能跑，先大拆 React god component 會把穩定線拉進風險區。
- 目前最大的工作台不穩，不是 UI 不漂亮，而是「一鍵失敗後工程師無法完整還原現場」。
- Run Log 是 Failure Card、Replay、Pilot List、Debug Bundle、工程師救援的共同依賴。
- App.tsx 拆分應該等 run log 與 guard tests 先落地，拆的時候才有防回歸網。

---

## 1. 已核對的現況

目前專案已具備：

- React `IsoPdfAutopilot()`，含 `isoView: "autopilot" | "workbench" | "engineer"`。
- 一鍵狀態雛形：`oneClickStage: "idle" | "running" | "applying" | "review" | "done"`。
- 前端 IPC wrapper：`discover_sources`, `split_pdf`, `load_iso_table`, `plan`, `build_rename_plan`, `export_plan_csv`, `start_batch_detect`, `job_status`, `cancel_job`, `apply`, `load_profile`, `save_profile`。
- Python bridge `launcher/app/tauri_iso_workflow.py` 已有上述 action 分派。
- Batch worker `tauri_iso_worker.py` 已有 `job.json` / events / progress 的暫態機制。
- Profile 以 `IsoNamingProfile` + `StateStore.iso_naming_profile(folder)` 儲存。
- PyQt6 ISO tests 與 Tauri ISO tests 已存在，後續不能破壞。

目前缺口：

- 沒有穩定的 `run_id` / run log store。
- 失敗時沒有可交給工程師的完整現場。
- `job.json` 是暫態，不適合當長期診斷資料。
- Profile 調校與一鍵預設尚未硬性分成 draft / published。
- Pilot List 尚未成為可測、可匯出的診斷模型。
- React ISO UI 大量集中在 `App.tsx`，但這是 P2 重構，不是 P0。

---

## 2. 三層產品邊界

### 一鍵 Autopilot

使用者：長官、一般同事、日常批次作業者。

保留：

- 選資料夾或使用自動探索。
- 一顆情境主按鈕。
- 六步驟 pipeline 摘要。
- 成功 / 警告 / 阻擋摘要。
- 失敗時複製問題摘要、匯出問題包、開啟工作台。

禁止出現：

- ROI 滑桿或拖框。
- ISO sheet / column 下拉。
- Pattern editor。
- Confidence threshold。
- Pilot List。
- Raw Run Log / JSON / traceback。
- 舊版 PyQt6 橋接按鈕。

### 工作台 Workbench

使用者：校對者、工程師、收到一鍵錯誤後的救援者。

應該做：

- 看命名表與問題列。
- 搜尋、只看問題、跳下一個問題。
- Inline 修 serial / line / new name。
- 看 PDF 預覽與 ROI 裁切結果。
- 採用判讀值、確認此列。
- 重新產生 draft。
- Dry-run、套用、匯出 CSV。
- 讀取 run log 還原現場。

不應該做：

- 直接拖 ROI 框。
- 調 OCR threshold。
- 看 raw stack trace。
- 改全域 profile published 設定。

### 調校 Engineer

使用者：開發者、進階工程師、圖框/OCR/欄位根因排查者。

應該做：

- ROI 拖框與多頁採樣。
- Confidence distribution / heatmap。
- Sheet / column mapping 詳細診斷。
- Pattern editor。
- Profile draft / publish / revert / history。
- Pilot List 完整檢視。
- Run Log / Replay / Debug Bundle。
- Developer mode 才顯示 raw JSON 與 traceback。

---

## 3. P0 執行路線

P0 目標：不破壞一鍵正常流程，只把「失敗能被工程師接住」接起來。

### A1. Run Log 落地

新增建議：

- `launcher/plugins/iso_tools/run_log.py`
- `tests/test_iso_run_log.py`

擴充：

- `launcher/app/tauri_iso_workflow.py`
- `launcher/app/tauri_iso_worker.py`

Run log 存放：

```text
.runtime/runs/iso/<run_id>/
  run.json
  events.jsonl
  plan.csv
  index.json
```

最低 schema：

```json
{
  "schema_version": 1,
  "run_id": "iso-20260608-143312-3f9a",
  "run_type": "autopilot",
  "status": "running",
  "created_at": "2026-06-08T14:33:12+08:00",
  "updated_at": "2026-06-08T14:33:18+08:00",
  "inputs": {},
  "profile": {},
  "stages": [],
  "summary": {},
  "rows": [],
  "failure": null,
  "replay": {}
}
```

驗收：

- 一鍵 / plan / apply 失敗時一定寫出 run log。
- `failed_stage`, `user_summary`, `developer.stack`, `replay` 必須存在。
- Happy path 也要能寫 completed run log。
- 測試不依賴真實使用者資料夾。

### A2. 一鍵失敗卡

新增建議：

- `frontend/tauri-spike/src/iso/components/FailureCard.tsx`

前端接入：

- 只在一鍵失敗或 review blocked 時顯示。
- 不改一鍵正常 pipeline 主流程。

卡片內容：

```text
這批沒有完成
原因：ISO List 讀到 0 筆，通常是 sheet 或欄位選錯。
已保留現場：iso-20260608-143312-3f9a

[複製給工程師] [匯出問題包] [開啟工作台]
```

三顆按鈕：

- 複製給工程師：複製 run_id + user_summary + 來源摘要。
- 匯出問題包：呼叫 `export_debug_bundle`。
- 開啟工作台：切到 workbench / engineer，載入該 run log。

驗收：

- Autopilot DOM 不出現 ROI、threshold、raw JSON、legacy bridge。
- 失敗卡只顯示人話摘要，不顯示 stack trace。

### A3. Debug Bundle

新增建議：

- `launcher/plugins/iso_tools/debug_bundle.py`
- `tests/test_iso_debug_bundle.py`

新增 action：

- `export_debug_bundle`

預設 zip 內容：

```text
iso_debug_<run_id>.zip
  run.json
  events.jsonl
  plan.csv
  profile.json
  pilot.json
  env.json
  README.txt
```

安全規則：

- 預設不包含原始 PDF / xlsx。
- 只放路徑、檔名、大小、sha1 摘要。
- 若未來要包含原始檔，必須另有明確勾選與警告。

### A4. Profile draft / published 分層

問題：

- 調校動作若直接寫入現有 profile，可能污染一鍵預設。

建議：

```text
profile published: 一鍵讀取的穩定設定
profile draft: 調校中的暫存設定
profile history: 發布前保留上一版
```

新增或調整 action：

- `load_profile`
- `save_draft_profile`
- `publish_profile`
- `revert_profile`

保守過渡：

- 舊 `save_profile` 先保留，但前端調校流程改呼叫 draft / publish。
- 一鍵只讀 published。

驗收：

- 調 ROI 後不會改變 published。
- 按發布後才更新一鍵會讀到的設定。
- 可回復上一版。

---

## 4. P1 執行路線

P1 目標：讓工作台能修問題，讓工程師能定位。

### B1. Pilot List 最小可用版

新增：

- `launcher/plugins/iso_tools/pilot.py`
- `tests/test_iso_pilot.py`

先做 12 項即可，不必一開始追求 18 或 37 項：

```text
P01 input discovery
P02 pdf source check
P03 page split check
P04 iso list parse
P05 sheet / column mapping
P06 serial detection
P07 iso correction
P08 duplicate serial
P09 missing serial
P10 naming pattern
P11 rename draft
P12 apply readiness
```

每項欄位：

```python
id
stage
status: pending | running | ready | warn | blocked | skipped
user_text
engineer_detail
metrics
auto_fix
manual_hint
blocks_apply
issue_codes
```

驗收：

- Pilot report 可從目前 request / plan / job result 建出。
- Validator 既有 checklist 是 Pilot List 的子集，不破壞現有 7 閘門。

### B2. Run Log Drawer / Replay

新增：

- `list_run_logs`
- `read_run_log`
- `replay_run_log`

前端：

- 工作台或調校右側 drawer 顯示最近 run。
- 點 failed run 自動定位 failed stage。
- Replay 只能 dry-run，不自動 apply。

驗收：

- 從 run_id 可回填 input/profile/rows/pilot。
- Replay 不寫 published profile。
- Replay 不自動更名。

### B3. 工作台問題列閉環

優先修現有體感不穩處：

- `下一個問題` 改成循環，不只跳第一個。
- 命名表支援狀態排序與 confidence 排序。
- 問題列分色：低信心、ISO 無對應、重複、blocked、manual corrected。
- `採用判讀值` / `確認此列` / `下一問題` 固定在右側檢視器。
- blocked 存在時 apply 永遠禁用。

驗收：

- 修正 blocked row 後狀態能轉 ready/warn。
- warn 必須確認後才能套用。
- CSV 匯出保留 manual correction 記錄。

---

## 5. P2 執行路線

P2 目標：大改版工作台與調校，但要在 P0/P1 的測試網完成後做。

### C1. 拆 App.tsx

拆分方向：

```text
frontend/tauri-spike/src/iso/
  IsoBoard.tsx
  AutopilotView.tsx
  WorkbenchView.tsx
  EngineerView.tsx
  components/
    PipelineSteps.tsx
    OneClickButton.tsx
    NamingTable.tsx
    IsoVisualPanel.tsx
    FailureCard.tsx
    PilotListDrawer.tsx
    RunLogDrawer.tsx
    EventLog.tsx
  hooks/
    useIsoWorkflow.ts
    useIsoMachine.ts
    useBatchJob.ts
    useRunLog.ts
    useRoiTuning.ts
```

拆分守則：

- 第一階段只搬檔，不改行為。
- 搬一塊跑一次 frontend build。
- 一鍵 guard test 先存在才拆 Autopilot。
- PyQt6 legacy 不動。

### C2. ROI 拖框與多頁採樣

新增：

- `RoiOverlay.tsx`
- `RoiSamplePanel.tsx`
- `launcher/plugins/iso_tools/roi_calibration.py`

規則：

- 工作台只顯示唯讀 ROI 框。
- 調校才允許拖框。
- 拖框只寫 draft profile。
- 多頁採樣顯示 confidence distribution。

### C3. 狀態機形式化

狀態：

```text
waiting
input_ready
draft_generating
draft_ready
warn
blocked
manual_review
ready_to_apply
applying
applied
failed
replaying
tuning
```

守則：

- UI 不直接決定能不能套用，由 state machine guard 決定。
- `applying` 不可取消。
- `blocked` 不能 apply。
- `warn` 未確認不能 apply。
- `replaying` 強制 dry-run。

---

## 6. P3 / exe 前才做

目前還沒要包 exe，因此這些先排後：

- Sidecar 化 Python ISO workflow。
- Tauri native e2e in CI。
- PyQt6 退出評估。
- Rollback SQLite 完整生產版。
- Run log retention policy UI。
- Telemetry 或使用統計。

但 exe 前一定要有：

- 中文路徑測試。
- Windows 鎖檔測試。
- VS C++ / rc.exe / Rust / Node env check。
- Tauri browser fallback 與 native dev 都能啟動。
- Debug bundle 隱私確認。

---

## 7. 測試入口

後端 ISO 聚焦：

```powershell
pytest (Get-ChildItem tests -Filter 'test_iso*.py' | ForEach-Object { $_.FullName }) -q
```

Tauri / frontend：

```powershell
.\scripts\test.ps1 -Suite frontend
.\scripts\test.ps1 -Suite tauri-ui
```

新增 P0 後至少要跑：

```powershell
pytest tests/test_iso_run_log.py tests/test_iso_debug_bundle.py tests/test_tauri_iso_workflow.py -q
.\scripts\test.ps1 -Suite frontend
.\scripts\test.ps1 -Suite smoke
```

---

## 8. 不准動清單

除非另開任務，P0/P1 不准：

- 拔掉 PyQt6。
- 刪除 `launcher/ui/iso_pdf_naming_dialog.py`。
- 把一鍵改成工程師畫面。
- 在 React 端重刻 Python 的命名判斷核心。
- 改變一鍵 happy path 的正常按鈕流程。
- 讓調校自動寫入 published profile。
- Debug bundle 預設打包原始 PDF / xlsx。

---

## 9. 下一個 Codex 任務建議

建議第一個實作任務：

**A1 — Run Log 落地**

任務範圍：

- 新增 `launcher/plugins/iso_tools/run_log.py`
- 新增 `tests/test_iso_run_log.py`
- 在 `launcher/app/tauri_iso_workflow.py` 的 `run_iso_workflow` action 外層記錄 run start / success / failure
- 在 `tauri_iso_worker.py` append events.jsonl

不准動：

- `frontend/tauri-spike/src/App.tsx` 一鍵正常流程
- `launcher/ui/iso_pdf_naming_dialog.py`
- PyQt6 legacy files

驗收：

- malformed ISO 或缺欄位時會寫 failed run log。
- run log 含 replay payload、user_summary、developer stack。
- happy path completed log 可讀回。
- 既有 ISO tests 不退步。

---

## 10. 三方文件取捨表

| 主張 | DeepSeek | Opus | Qwen | 統整裁決 |
| --- | --- | --- | --- | --- |
| 三層分離 | 強 | 強 | 強 | 採用 |
| 一鍵不塞工程資訊 | 強 | 強 | 強 | 採用，並加 guard test |
| Run Log / Replay | 強 | 最強 | 強 | P0 第一順位 |
| Pilot List | 18 項 | 17 項 | 17+ 項 | P1 先做 12 項最小可用，再擴 |
| Debug Bundle | 有 | 強 | 有 | P0 |
| Profile draft/published | 有 | 強 | 有 | P0 |
| 先拆 App.tsx | 中 | P2 | 強 | 延後到 P2 |
| ROI 拖框 | P1/P2 | P1/P2 | P2 | P2，因為會動 UI 與 profile |
| PyQt6 退出 | exe 前 | developer-only 過渡 | exe 前 | 不拔，只逐步退到 developer-only |

---

## 11. 最短落地順序

```text
1. run_log.py + tests
2. export_debug_bundle + tests
3. FailureCard，只接一鍵失敗狀態
4. profile draft/published
5. Pilot List 12 項
6. Run Log Drawer + Replay dry-run
7. 工作台問題列閉環
8. ROI 調校 UI
9. App.tsx 拆檔
10. exe 前完整 e2e / rollback / PyQt6 退出評估
```

這條順序的好處：

- 先讓一鍵出問題時有資料可救。
- 再讓工作台有結構化診斷。
- 最後才大改 UI，避免在沒有測試網時把穩定的一鍵拆壞。
