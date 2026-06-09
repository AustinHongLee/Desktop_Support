# ISO PDF Pilot 升級 — 完成狀態與後續交接

> Date: 2026-06-09
> Branch: `codex/tauri-react-spike`
> Status: main uplift complete; this file replaces the earlier stale "Batch 1-5 todo" handoff.
> Docs index: `docs/iso_pdf_current_status.md`

---

## 0. 結論

本輪主線已完成：Pilot 已從 run log 診斷資料升級為一鍵 / 工作台 / 調校共用的流程導引。

已落地範圍：

- Batch 1: Pilot schema v2、前端型別 / helpers、共用 `PilotStrip` / `PilotListPanel`
- Batch 2: 工作台 Pilot summary、問題導航、表格版面修正
- Batch 3: 調校 Pilot List、P13-P15、`roi_distribution`
- Batch 4: 一鍵 Pilot 投影、成功摘要、失敗最可能原因
- Batch 5: targeted tests、1181x790 / 寬版 layout polish、樣本驗證
- 補修: ROI slider debounce，避免開啟影像判讀時每個滑桿事件都重跑 preview/OCR 造成 Tauri 卡死

目前不是「請接 Batch 3-5」的狀態；舊說法已過期。

---

## 1. 不可改壞的契約

1. `P01`-`P12` 的 `id` / `stage` 已是持久化契約，禁止重新編號。
2. 新檢查只能 append，例如目前已 append `P13`-`P15`。
3. `PILOT_STATUSES` 仍固定為 `pending/running/ready/warn/blocked/skipped`。
4. stale / review 類狀態用附加欄位表達：
   - `freshness: "fresh" | "stale"`
   - `needs_review: boolean`
   - `next_action`
5. 一鍵流程的 `oneClickStage` / `runOneClick` 主行為不可為了 UI 投影而改壞。
6. PyQt6 legacy 保留作對照與備援，不刪除。
7. `run_iso_workflow` 既有 action schema 不破壞；新增能力用新 action。

---

## 2. 已完成的主要檔案

後端：

- `launcher/plugins/iso_tools/pilot.py`
  - `PILOT_SCHEMA_VERSION = 2`
  - append `P13 roi_confidence`
  - append `P14 profile_consistency`
  - append `P15 draft_freshness`
  - P13 以使用者門檻判斷，避免「0 頁需確認」卻亮黃
- `launcher/app/tauri_iso_workflow.py`
  - `roi_distribution` action
- `launcher/app/tauri_iso_worker.py`
  - batch result source 保留 `confidence_threshold / serial_region / drawing_region`
  - 避免 P15 在 batch 結果誤判 stale
- `launcher/plugins/iso_tools/roi_calibration.py`
  - `confidence_distribution` 被 Tauri 路徑使用

前端：

- `frontend/tauri-spike/src/isoWorkflow.ts`
  - Pilot schema v2 optional fields
  - `loadIsoRoiDistribution`
- `frontend/tauri-spike/src/iso/helpers.ts`
  - Pilot label / tone / next action / display localization
- `frontend/tauri-spike/src/iso/IsoBoard.tsx`
  - live `plan.pilot_results` 接入工作台、調校、一鍵
  - Pilot jump / stale 判斷 / 一鍵 pipeline 推導
  - ROI preview debounce，避免 slider 連續觸發 OCR
- `frontend/tauri-spike/src/iso/WorkbenchView.tsx`
  - PilotStrip 與問題導引
- `frontend/tauri-spike/src/iso/EngineerView.tsx`
  - 調校頁三欄重整
  - PilotListPanel / RoiSamplePanel / legacy fallback
- `frontend/tauri-spike/src/iso/AutopilotView.tsx`
  - 一鍵頁只顯示人話進度、成功摘要、失敗最可能原因
- `frontend/tauri-spike/src/iso/components/*`
  - `PilotStrip`
  - `PilotListPanel`
  - `RoiSamplePanel`
  - `FailureCard`
  - `IsoVisualPanel`
- `frontend/tauri-spike/src/styles.css`
  - 調校頁 1181x790 / 寬版布局修正

測試：

- `tests/test_iso_pilot.py`
  - schema v2
  - P13 / P14 / P15
  - P15 stale
  - P14 missing paths block apply
  - batch result tuning fields
  - `roi_distribution`

---

## 3. 驗證結果

最後已跑過：

```powershell
.\scripts\test.ps1 -Suite frontend
python -m pytest tests\test_iso_pilot.py tests\test_iso_one_click_workflow.py tests\test_iso_debug_bundle.py
git diff --check
```

已確認：

- frontend build 通過
- targeted Python tests 通過
- `git diff --check` 只有 CRLF warning，無 whitespace error
- 樣本 `C:\Users\a0976\Downloads\t` batch worker:
  - rows: `4 ready / 0 warn / 0 blocked`
  - Pilot: `15 ready / 0 warn / 0 blocked`
- 調校頁:
  - 1181x790 無水平溢出
  - 寬版右欄不再壓縮主預覽
  - Pilot / ROI / legacy fallback 顯示正常
- 一鍵頁:
  - 不顯示 ROI / raw JSON / P 代號清單
  - pipeline 使用人話狀態

---

## 4. 目前可視為完成的驗收項

| 項目 | 狀態 |
|---|---|
| Batch 1 Pilot 型別 / helper / schema v2 | done |
| Batch 2 工作台 Pilot summary / 問題導航 | done |
| Batch 3 調校 Pilot List / P13-P15 / ROI distribution | done |
| Batch 4 一鍵導引 / 失敗橋接 | done |
| Batch 5 targeted tests / layout polish | done |
| ROI slider 卡死風險 | fixed by debounce |
| 文件去舊化 | done; see `docs/iso_pdf_current_status.md` |

---

## 5. 仍可選做，但不是本輪 blocker

這些不是「主線未完成」，只是之後可加強：

1. P16 `export_log`
   - CSV / run log / debug bundle 匯出就緒檢查。
2. P17 `apply_safety`
   - 目標檔案鎖定 / rollback 可用性 / 實際套用前磁碟安全。
3. stateMachine apply guard 改吃 Pilot `blocks_apply`
   - 需先寫對拍測試確認與現有 row 計數等價。
4. 更完整的 Tauri UI 自動測試
   - 現在主要靠 frontend build、pytest、手動 / browser smoke。
5. 舊 PyQt validator 與 Tauri Pilot 的長期收斂
   - legacy 仍保留，不急著刪或重寫。

---

## 6. 下一輪快速檢查

若下一輪要確認狀態，先跑：

```powershell
git status --short --branch
git log --oneline -6
.\scripts\test.ps1 -Suite frontend
python -m pytest tests\test_iso_pilot.py tests\test_iso_one_click_workflow.py tests\test_iso_debug_bundle.py
```

樣本資料：

```text
C:\Users\a0976\Downloads\t
```

期望：

- `testing_pages`: 4 pages
- batch result: `4 ready / 0 warn / 0 blocked`
- Pilot result: `15 ready / 0 warn / 0 blocked`

---

## 7. 相關文件

- 目前索引：`docs/iso_pdf_current_status.md`
- 歷史設計檔案：`docs/archive/iso_pdf/`
- 設計總綱：`docs/archive/iso_pdf/iso_pdf_pilot_uplift_plan_2026-06-09.md`
- 三方統整與邊界裁決：`docs/archive/iso_pdf/iso_pdf_workbench_integrated_execution_plan_2026-06-08.md`
- 原始 17 項設計參考：`docs/archive/iso_pdf/iso_pdf_next_stage_design_2026-06-08.md`
- 注意：archive 內的 audit / blueprint / pilot plan 是設計歷程，不代表目前實作狀態。
