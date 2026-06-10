# ISO Node Workflow C Phase 施工書

> Date: 2026-06-10
> Base: `codex/tauri-react-spike` @ `4b6bb05`（fix(iso-workflow): store apply records in run artifacts (B11)）
> 前篇：`docs/iso_pdf_workflow_next_phase_plan_2026-06-10.md`（B5-B9 + Postscript B10-B11，封存）
> 本文件是 C 期唯一 active 施工入口。所有引用的函式名/行號都對照 `4b6bb05` 實碼驗證過。
> 施工分支：`codex/iso-workflow-c`。實驗樣本：`C:\Users\a0976\Downloads\t`。

---

## 1. 現況摘要

主線 commit 鏈（全部已合併、已驗證存在）：

```text
74e6ad9 merge B1-B4 ─ 268cc30 B5 prep ─ a73374f B5 投影 ─ 72acef1 B6 工作台唯讀面板
─ 09bd563 B7 parity harness ─ a083157 B8 調校 overlay ─ eba3e15 B9 節點式分頁+flowAdapter
─ 2ae7b44 merge consume-v1 ─ 4373b05 B10 CSV guarded ─ 4b6bb05 B11 apply 記錄進 artifacts
tags: iso-workflow-poc-v1, iso-workflow-consume-v1
```

能力盤點：

| 層 | 現況 |
|---|---|
| Engine | schema/registry/policy/executor/run log/replay/artifact hydration 完整；12 ISO nodes；CLI `list-nodes/validate/run/run-node/replay/list-runs/parity` |
| Backend bridge | 10 個 workflow action：list_nodes/load/validate/run/run_status/cancel/list_runs/read_run_log/plan_from_run/read_artifact；job dir + polling（`tauri_workflow_job.py`） |
| 投影 | `projection.py`：`plan_from_run`（batch_detect.result 優先、pilot 覆蓋、summary 重算、provenance）+ `read_artifact`（64MB 上限、resolve 逃逸檢查） |
| Parity | `parity.py` + CLI `parity`（exit 0=equal / 6=violation）+ `tests/test_iso_workflow_parity.py`（golden/smoke/變異哨兵/real-sample skipUnless） |
| 前端 | 四分頁 `autopilot/workbench/engineer/nodes`（IsoBoard L116）；工作台 `WorkflowRunPlanPanel`（唯讀、不接 apply）；調校 overlay（`buildWorkflowInputsOverlay`）+ 顯式驗證鈕；節點式分頁 = WorkflowInspector + graph JSON + `flowAdapter.ts`（vitest 3 測試） |
| 四模式關係 | 一鍵=legacy 路徑（未換軌）；工作台=可唯讀消費 workflow run；調校=inputs overlay 顯式驗證；節點式=唯讀檢視 + safe-run。**workflow 仍是影子系統，一鍵的真實執行 100% 走 legacy** |

## 2. 已完成且不可回退的安全契約（C 期任何 phase 不得觸碰）

1. `GUARDED = {renames_files, writes_profile, writes_csv}`；`REPLAY_HARD_BLOCKED` = 同三項（policy.py L27-28）。**writes_csv 永遠不回 AUTO_ALLOWED。**
2. 前端不存在傳遞 `workflow_allow` / `workflow_confirm` 的程式路徑；`runIsoNodeWorkflowSafe` 簽名無此參數。真 rename / 寫 profile / 寫 CSV（經 workflow）只有 CLI 三因子（graph `enabled:true` + `--allow` + `--confirm`）。
3. apply 前**不自動** export CSV；apply 更名記錄 = `.runtime/runs/iso/<run_id>/artifacts/apply_rename_record.csv`（runtime artifact，非使用者輸出）。
4. safe mode / Inspector safe run 不得在使用者工作資料夾產生任何 `iso_rename_plan_*.csv`。
5. `workflow_run` / OCR / batch_detect 只能由使用者點擊觸發；useEffect/onChange/輪詢 callback 永不執行。
6. Pilot P01-P15 id/stage 凍結 append-only；不動 PyQt legacy；`.qwen/` 永不 stage；不破壞既有 21 個 ISO action schema。

## 3. Deepseek V4 Pro 壓力測試結論摘要

針對 `C:\Users\a0976\Downloads\t` 與 `.runtime` 殘留追蹤，確認 `iso_rename_plan_*.csv` 污染有三個來源：(1) safe POC graph 內含會被執行的 `export_csv` 節點；(2) `writes_csv` 當時是 AUTO_ALLOWED，寫 CSV 不需授權；(3) React/Tauri apply 流程在真正更名前先呼叫 `exportIsoPlanCsv()`，把「更名記錄」與「使用者匯出」混在同一條路徑，預設寫進工作資料夾且時間戳檔名無限累積。三者疊加 = 每次安全測試都在使用者資料夾留垃圾。

留給 C 期的未決項（本文件裁決）：手動匯出的預設路徑/檔名/retention（→C2）、Excel 鎖檔錯誤（→C2）、壓力測試自動化（→C1）、節點畫布的 guarded 鎖定語言（→C4）。

## 4. B10-B11 修正後的新基線

- **B10 `4373b05`**：`writes_csv` → GUARDED + REPLAY_HARD_BLOCKED；`iso.export_plan_csv` spec 標 guarded；safe POC 的 `export_csv` 節點 `enabled=false, requires_confirm=true`；節點式 UI 把 CSV 顯示為 guarded；新增「safe run 不產生 iso_rename_plan_*.csv」測試。
- **B11 `4b6bb05`**：apply/one-click apply 移除 `exportIsoPlanCsv()` 前置呼叫；後端 `apply` 寫 `iso_run_root()/<run_id>/artifacts/apply_rename_record.csv`（L670），response 回 `record_path`/`record_row_count`（L657-658）。手動「匯出 CSV」保留（IsoBoard L851 `exportIsoPlanCsv`），但其後端預設路徑**仍是**使用者資料夾 + 時間戳（`_default_export_path` L972-989：page_folder → combine 旁 → work_folder → iso_list 旁）——這是 C2 的施工對象，不是回歸。

## 5. C 期目標

**一句話**：把 B10-B11 的防爆成果固化成自動化回歸（誰都改不壞），收乾最後一條會寫使用者資料夾的預設路徑（手動匯出），補強前端執行韌性，然後在「零新增執行路徑」的前提下給節點式一張唯讀畫布，並建立一鍵換軌的證據累積機制。

**做到哪裡停**：C5 結束（merge + tag `iso-workflow-c-v1`）即停工。一鍵換軌本體（shadow flag / 替換）是 D 期，開工條件寫在 C5。

**C 期裁決總表**（對應任務書四個評估方向）：

| 方向 | 裁決 | 進 C 期？ |
|---|---|---|
| CSV 手動匯出策略 | 預設改 `.runtime/exports/iso/`、保留時間戳檔名、retention 保留最近 50 份、Excel 鎖檔友善錯誤；使用者明示路徑永遠優先且不受限 | ✅ C2 |
| 壓力測試自動化 | 全部轉成 pytest 可重複測試 + 把前端安全規則寫成「讀原始碼的靜態守門測試」 | ✅ C1 |
| 節點式 UI 下一步 | **接 @xyflow/react，但唯讀**：畫布零執行能力、guarded 鎖定視覺契約先行；編輯能力是 D 期 | ✅ C4 |
| 一鍵換軌 | **還不換**。parity harness 存在但證據量不足（fixtures + 單次 real sample）；C5 建立 parity 歷史累積 + 換軌 gate 定義；D 期才做 shadow run → 替換 | 部分 ✅ C5 |


---

## 6. Phase-by-Phase 施工書（C1-C5）

> 通則：每 phase 一個 commit + push；C1/C2 backend 為主、C3/C4 frontend、C5 收尾。C1 與 C4 絕不混做（防爆測試先於畫布存在，畫布才有東西守）。每 phase 結束：測試命令全綠 → `git diff --stat` 對照檔案清單無越界 → commit。

### C1 — 防爆回歸自動化 + 兩個後端小修補（backend）🟢

- **目標**：把 Deepseek 發現的每一類爆點固化成永久回歸測試；順手修掉驗證中發現的兩個真實漏洞（run_id 路徑逃逸、workflow apply 記錄一致性）。
- **修改檔案範圍**：
  - 新增 `tests/test_iso_workflow_pollution.py`（防污染回歸主檔）
  - 新增 `tests/test_frontend_safety_contract.py`（讀前端原始碼的靜態守門測試，純標準庫）
  - 修改 `launcher/app/tauri_iso_workflow.py`（僅 `_workflow_run_dir_required` 一處，見下）
  - `tests/test_tauri_iso_workflow.py` append 逃逸測試
- **實作細節**：
  1. **修補 `_workflow_run_dir_required`（L1261-1271）**：現行 L1265-1267 `candidate = Path(run_id); if candidate.exists() and candidate.is_dir(): return candidate` 接受**任意既存目錄**當 run dir——`workflow_run_id` 變成裸路徑參數，`workflow_read_run_log`/`plan_from_run`/`read_artifact` 可被導向任意資料夾。修法：保留絕對路徑便利分支，但加 `resolve()` 後必須位於 `_workflow_run_root().resolve()` 之下，否則 `ValueError("workflow_run_id 不可指向 run root 以外路徑。")`；CLI 不受影響（CLI 自己組路徑）。
  2. `test_iso_workflow_pollution.py`（全部用 `PROJECT_ROOT_ENV`/`STATE_PATH_ENV` 改道 tmp、pypdf+openpyxl 生成 fixture、monkeypatch `_spawn_iso_worker`→同步 `run_job`、`_spawn_workflow_job`→同步執行）：
     - `test_safe_run_x10_no_csv_pollution`：同一工作資料夾連跑 safe POC **10 次** → 斷言 work folder 與其子樹 `glob("**/*.csv")` 僅含 fixture 自帶檔；`iso_rename_plan_*` 計數 = 0；且 10 次 run dir 各自獨立存在。
     - `test_apply_writes_record_artifact_only`：走 backend `apply`（main() 路徑、帶 run log）→ `apply_rename_record.csv` 存在於 `.runtime/runs/iso/<run_id>/artifacts/`；work folder 零新 CSV；response 含 `record_path`。
     - `test_workflow_apply_keeps_workdir_clean`：workflow 路徑 apply（CLI 三因子、tmp fixtures）→ work folder 除被更名的 PDF 外零新檔。
     - `test_replay_blocks_csv_even_with_flags`：對含 enabled export_csv 的圖 replay + `--include-auto-side-effects` + allow/confirm 全給 → decision=`blocked_replay`、零 CSV。
     - `test_missing_pdf_and_missing_iso_list_fail_gracefully`：缺 combine/page → run status=failed、error 含中文訊息、無 partial CSV/rename；缺 iso_list 同。
     - `test_chinese_and_space_paths`：fixture 放在 `tmp/測試 資料夾 t/` 下全流程跑通（split/detect/plan/投影）。
     - `test_large_pdf_smoke`：生成 60 頁 PDF（pypdf 迴圈）→ batch_detect（detect_serials=false）完成、progress 單調遞增、`job.json` 最終 rows=60、耗時上限 120s（防 O(n²) 退化哨兵）。
  3. `test_frontend_safety_contract.py`（把 grep 守門變成可重複測試；讀 `frontend/tauri-spike/src/**/*.ts*` 原始碼字串）：
     - `workflow_allow|workflow_confirm` 出現次數 = 0（型別定義檔 `isoWorkflow.ts` 的 interface 欄位除外——精確規則：僅允許出現在 `IsoWorkflowRequest` interface 區塊內）。
     - `runIsoNodeWorkflowSafe(` 呼叫點 ≤ 2（定義 + Inspector 內唯一呼叫）。
     - `useEffect` 區塊內不得含 `workflow_run`、`startIsoBatchDetect`、`runIsoNodeWorkflowSafe`（以縮排塊掃描，誤報寧可手動豁免清單）。
     - safe POC json：`export_csv` 節點 `enabled === false`、`apply_rename` 節點 `enabled === false`。
     - `policy.py`：斷言三個集合內容（防止未來 refactor 默默放寬）。
- **禁止事項**：不改 engine 行為（修補僅限 action 層路徑檢查）；不動前端；不放寬任何集合；測試不得寫真實 `Downloads\t`。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py tests\test_tauri_iso_workflow.py -q
  & .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_engine.py tests\test_iso_workflow_policy.py tests\test_iso_workflow_job.py tests\test_iso_workflow_projection.py tests\test_iso_workflow_parity.py -q
  ```
- **驗收標準**：上列全綠；故意把 `writes_csv` 搬回 AUTO_ALLOWED 跑守門測試必紅（驗完改回來，這條只做一次性人工確認哨兵有效並記進 commit message）。
- **Rollback 風險**：測試純新增；`_workflow_run_dir_required` 修補可能擋掉「曾用裸路徑呼叫」的內部用法——全 repo grep `workflow_run_id` 確認呼叫端只傳 run_id 字串即可（驗證過 Inspector 只傳 `next.workflow_run_id`）。revert 單 commit 還原。
- **Commit**：`test(iso-workflow): add anti-pollution regression suite and run dir guard (C1)`
- **🟢 Checkpoint**：可停下交接。

### C2 — 手動 CSV 匯出策略統一（backend 為主，前端僅訊息）

- **目標**：手動「匯出 CSV」不再預設寫使用者工作資料夾；給 retention；Excel 鎖檔給人話錯誤。使用者明示路徑永遠優先。
- **裁決**（對應任務書三-1）：
  | 問題 | 裁決 | 理由 |
  |---|---|---|
  | 固定檔名 or 時間戳 | **保留時間戳** `iso_rename_plan_<YYYYMMDD_HHMMSS>.csv` | 固定檔名 + Excel 開著 = 每次匯出都撞鎖；時間戳 + retention 兩全 |
  | 預設位置 | **`.runtime/exports/iso/`**（`runtime_root()/.runtime/exports/iso/`） | 工作資料夾零污染是 B10 的核心戰果；預設值守住，找檔靠 response 顯示完整路徑 |
  | retention | **保留最近 50 份**，每次匯出後修剪（按 mtime 排序刪舊，刪除失敗（鎖檔）靜默跳過並記 issue） | 50 份 ≈ 數 MB，夠回溯又不無限長 |
  | 使用者明示 `export_path` | 原樣尊重，寫哪都行、不修剪、不改名 | 明示意圖高於預設政策 |
  | Excel 鎖檔 | 捕 `PermissionError`/`OSError(winerror=32/33)` → `ValueError("CSV 正被其他程式（例如 Excel）開啟，請關閉後重試：<path>")`；寫入用 tmp+`os.replace`，replace 失敗同訊息 | 現行裸 traceback 對使用者無意義 |
- **修改檔案範圍**：
  - 修改 `launcher/app/tauri_iso_workflow.py`：`_default_export_folder()` 改回傳 `runtime_root()/.runtime/exports/iso`（原四層 fallback 刪除）；`export_plan_csv()` 加鎖檔錯誤包裝 + tmp 原子寫 + 匯出後 `_prune_exports(keep=50)`（新私有函式）；response 增 `export_dir` 欄位。
  - 修改 `frontend/tauri-spike/src/isoWorkflow.ts`（`IsoExportResult` append `export_dir?: string`）
  - 修改 `frontend/tauri-spike/src/iso/IsoBoard.tsx`（L851 匯出成功訊息改含完整路徑 + 「複製路徑」既有訊息機制；**不**引入 shell-open 權限）
  - `tests/test_tauri_iso_workflow.py` / `tests/test_iso_workflow_pollution.py` append：預設匯出落在 exports dir、明示路徑優先、retention 修剪第 51 份、鎖檔錯誤訊息（monkeypatch `Path.open` raise `PermissionError`）。
- **禁止事項**：不恢復 apply 前自動 export；不動 `iso.export_plan_csv` 的 guarded 分類；workflow export 節點走同一個 `_default_export_folder`（自動繼承新預設，不另寫一套）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_tauri_iso_workflow.py tests\test_iso_workflow_pollution.py tests\test_iso_workflow_nodes.py -q
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build
  ```
- **驗收標準**：手動匯出（無 export_path）→ 檔案在 `.runtime/exports/iso/`、工作資料夾乾淨；51 份觸發修剪；鎖檔訊息含中文與路徑；C1 的 10 次 safe run 測試仍綠。
- **Rollback 風險**：使用者若已習慣「CSV 出現在工作資料夾」會察覺行為變化——這是**有意的**，在 commit message 與 §9 禁止事項記明；revert 單 commit 可回。`_default_export_folder` 也被 export 節點與測試引用，跑全套確認。
- **Commit**：`feat(iso-workflow): route manual csv exports to runtime exports dir with retention (C2)`


### C3 — Inspector / workflow job 前端韌性（frontend）

- **目標**：堵住「分頁切換丟失執行中 job」這個真實雙跑漏洞：workflow job 狀態提升到 IsoBoard、重入時恢復輪詢、執行中全域防重複觸發。
- **問題實證**：`WorkflowInspector` 的 `job` 是元件內 `useState`；切到別的分頁元件 unmount → 狀態消失；切回來 `canRunSafe` 因 `job=null` 重新為 true，**後端 job 還在跑，使用者再點一次 = 同輸入雙併發 workflow_run**（兩個 worker 同時掃同一 page folder + 雙倍 OCR）。輪詢 effect 本身有 `cancelled` flag + `clearInterval` 清理（已驗），漏的是狀態存活。
- **修改檔案範圍**：
  - 修改 `frontend/tauri-spike/src/iso/IsoBoard.tsx`：新增 `workflowJob` state（`IsoNodeWorkflowJobPayload | null`）與 setter，props 傳入 Inspector；分頁鈕在 `isWorkflowJobRunning(workflowJob)` 時於「節點式」鈕顯示小執行中徽章（純顯示）。
  - 修改 `frontend/tauri-spike/src/iso/WorkflowInspector.tsx`：`job`/`setJob` 改用 props（保留無 props 時的本地 fallback 以利測試）；mount 時若 props job 非終態 → 直接恢復輪詢（沿用既有 effect，它本來就以 `isWorkflowJobRunning(job)` 為條件，state 提升後自然成立）；`requestSafeRun` 防重入：`isWorkflowJobRunning(job) || safeRunBusy` 時直接 return。
- **禁止事項**：不引入全域 store 套件（React state 提升就夠）；不改輪詢間隔；不加任何自動重跑；不動 AutopilotView/WorkbenchView/EngineerView 行為。
- **測試命令**：
  ```powershell
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit
  & .venv\Scripts\python.exe -m pytest tests\test_frontend_safety_contract.py -q
  ```
- **驗收標準**：tsc/build/vitest 綠；手動煙測一次（執行 safe run → 切到一鍵再切回節點式 → 進度仍在、按鈕 disabled、cancel 可用）；靜態守門：`runIsoNodeWorkflowSafe` 呼叫點數不變。
- **Rollback 風險**：state 提升是純搬移；revert 回元件內狀態（漏洞回歸但功能不壞）。
- **Commit**：`fix(iso-workflow): lift workflow job state to survive view switches (C3)`

### C4 — React Flow 唯讀畫布 + guarded 防爆 UI 契約（frontend）🟢

- **裁決：現在接 `@xyflow/react`，但只做唯讀。** 理由：(1) flowAdapter 資料模型 + vitest 測試在 B9 已落地，畫布只是渲染器；(2) C1 已把安全契約變成自動化測試，畫布想開後門會先弄紅測試；(3) 唯讀畫布零新增執行路徑，符合「安全 > 漂亮」。**編輯能力（拖線、改 params、enable 切換）全部是 D 期**，因為那需要 confirm UX 設計 + graph 寫回 API，兩者都還不存在。
- **Guarded side-effect 防爆 UI 契約（先於畫布程式碼存在，D 期編輯也必須遵守）**：
  1. 畫布是**純展示層**：任何畫布互動（點擊/拖曳/快捷鍵/右鍵）都不得直接或間接呼叫 `workflow_run`、不得修改 graph JSON。唯一執行入口維持 Inspector 既有 safe-run 鈕（畫布之外）。
  2. 三類 guarded（`renames_files`=更名、`writes_csv`=匯出、`writes_profile`=設定檔）在節點上必須同時呈現三件事：紅色🔒徽章、`disabled` 灰底（若 enabled=false）、tooltip 固定文案「guarded：需 CLI 三因子授權（--allow + --confirm + enabled）」。auto 類顯示黃色「自動允許」chip；純讀綠色。
  3. 節點點擊只開**唯讀**側欄（spec、params、最近一次 run 該節點的 status/side_effects/decision——資料來自既有 `readIsoWorkflowRunLog`）。側欄沒有任何按鈕會發 request（複製 JSON 除外）。
  4. 畫布不提供 minimap context menu、不註冊 `onConnect`/`onNodesDelete` 等編輯 handler（傳 `nodesConnectable={false}`、`nodesDraggable={true}`（僅視覺位置）、`deleteKeyCode={null}`、`edgesFocusable={false}`）。
  5. D 期若開放編輯：guarded 節點的 enable 切換必須走「輸入節點 id 全名確認」對話框 + 僅產生新 workflow 副本（永不覆寫 safe POC），且 allow/confirm 仍只存在於 CLI——此契約現在寫死在文件，D 期施工書必須引用。
- **修改檔案範圍**：
  - 修改 `frontend/tauri-spike/package.json`（dependency append `@xyflow/react@^12`；lockfile 一併 commit）
  - 新增 `frontend/tauri-spike/src/iso/WorkflowCanvas.tsx`（`graphToFlow` 餵 `<ReactFlow>`；自訂 `isoNode` 節點元件渲染 §契約-2 的徽章；`fitView`；上限保護：>60 節點不渲染改提示）
  - 修改 `frontend/tauri-spike/src/iso/WorkflowInspector.tsx`（節點式分頁 graph 區塊頂部 mount `<WorkflowCanvas payload={graph} runLog={runLog} onSelectNode={...} />` + 唯讀側欄；原 JSON `<details>` 保留）
  - 修改 `frontend/tauri-spike/src/iso/flowAdapter.ts`（如需補 `data` 欄位映射，append-only）+ `flowAdapter.test.ts` append 對應測試
  - `tests/test_frontend_safety_contract.py` append：`WorkflowCanvas.tsx` 內不得出現 `runIsoNodeWorkflowSafe|workflow_run|applyIsoPlan|exportIsoPlanCsv`
- **禁止事項**：不裝 @xyflow/react 以外任何套件；畫布不出現「執行」「啟用」「授權」字樣的可點元素；不改 flowAdapter 既有函式簽名；npm install 失敗（離線等）→ **停下回報，不准手寫 canvas 替代**。
- **測試命令**：
  ```powershell
  cd frontend\tauri-spike; npm install; npx tsc --noEmit; npm run build; npm run test:unit
  & .venv\Scripts\python.exe -m pytest tests\test_frontend_safety_contract.py -q
  ```
- **驗收標準**：safe POC 圖渲染 8 節點 + 推導邊；export_csv/apply_rename 呈灰底紅鎖；點節點開唯讀側欄含最近 run decision；build 產物大小增幅記進 commit message（預期 +~50KB gz）；守門測試綠。
- **Rollback 風險**：revert = 移除元件 + package.json/lockfile 回退，Inspector 回 JSON-only；無資料/後端風險。
- **Commit**：`feat(iso-workflow): readonly react-flow canvas with guarded lock language (C4)`
- **🟢 Checkpoint**：可停下交接。

### C5 — 換軌證據鏈 + 收尾（backend CLI + docs）

- **目標**：讓 parity 證據可累積、可查詢；定義 D 期一鍵換軌的開工 gate；收尾 merge + tag。
- **裁決**（對應任務書三-4）：換軌路徑 = **雙軌比較（C 期，手動觸發）→ shadow run（D 期，feature flag，一鍵照舊走 legacy、背景影子跑 workflow 並記 parity）→ 替換（D 期末）**。不直接替換：一鍵是使用者唯一信任路徑，沒有累積證據前不動。**不做** in-app 雙軌按鈕（雙軌=雙倍 OCR + 同 page folder 併發風險，留在 CLI 順序執行）。使用者人工驗證入口 = 工作台 `WorkflowRunPlanPanel`（看 workflow 結果）+ 本 phase 的 parity 歷史顯示（看比對結論）。
- **修改檔案範圍**：
  - 修改 `launcher/plugins/iso_tools/workflow/cli.py` + `parity.py`：parity report 預設落 `runtime_root()/.runtime/runs/parity/<ts>/report.json`；新增 CLI 子命令 `parity-history [--limit N] [--json]`（列最近 reports：ts/equal/violations 數/inputs digest）。
  - 修改 `launcher/app/tauri_iso_workflow.py`：append 唯讀 action `workflow_parity_history`（讀同一資料夾，回 `{reports: [...]}`；無寫入）。
  - 修改 `frontend/tauri-spike/src/isoWorkflow.ts`（type + helper `listIsoParityReports()`）與 `WorkflowInspector.tsx`（節點式分頁 append「換軌守門」小區塊：最近 parity 結果列表 + 固定文案顯示 CLI 指令供複製；**沒有**「執行比對」按鈕）。
  - 新增 `tests/test_iso_workflow_parity_history.py`；real-sample parity 跑一次（`C:\Users\a0976\Downloads\t`）把 report 留檔作為第一筆證據（結果原文進 commit message）。
  - docs：本文件 append 完工 postscript；`git tag -a iso-workflow-c-v1`；merge `codex/iso-workflow-c` → `codex/tauri-react-spike`（--no-ff）。
- **D 期換軌 gate（寫死）**：(1) parity-history 最近 **5 筆全 equal 且至少 2 筆來自 real sample**；(2) C1 防污染套件連續綠；(3) shadow run 設計書（D 期施工書）就緒。三者齊備 D 期才准動 `AutopilotView` 的執行路徑。
- **禁止事項**：不動一鍵任何執行程式碼；parity history 為唯讀 action；不在 UI 放執行比對的按鈕。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_parity.py tests\test_iso_workflow_parity_history.py tests\test_tauri_iso_workflow.py -q
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\poc_inputs.json --json
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli parity-history --json
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build
  ```
- **驗收標準**：parity report 持久化 + history 列得出；real sample 第一筆 equal（若 violation → 停工回報原文，這比 merge 重要）；全測試矩陣（§8）綠；merge + tag 完成。
- **Rollback 風險**：全部 append-only；revert 不影響 C1-C4。
- **Commit**：`feat(iso-workflow): persist parity evidence and define switchover gate (C5)`


---

## 7. 錯誤排除 Top 10（高價值爆點審查）

| # | 爆點 | 嚴重度 | 為什麼會爆 | 最可能位置 | 如何重現 | Codex 最小修補 | 進 C 期？ |
|---|---|---|---|---|---|---|---|
| 1 | CSV 污染回歸 | 🔴 高 | `writes_csv` guarded 只是一行 frozenset；任何 refactor / 新 node / 新 workflow JSON 把 export 節點 enabled 回來就回歸；`_default_export_folder` 仍指向使用者資料夾（手動匯出路徑） | `policy.py` L18-28、`workflows/iso_pdf_safe_poc.workflow.json`、`tauri_iso_workflow.py` L972-989 | 把 export_csv 節點 `enabled:true` 或集合搬回 AUTO，跑 safe run | C1 守門測試斷言集合內容 + safe POC 節點旗標 + 10 次 run 零 CSV；C2 收掉預設資料夾 | ✅ C1+C2 |
| 2 | run log / artifact 路徑逃逸 | 🔴 高 | `_workflow_run_dir_required` L1265-1267 接受任意既存目錄當 run dir → `workflow_run_id` 變裸路徑參數；projection 的逃逸檢查以該 dir 為基準，等於可指到任何資料夾讀 `run_log.json`/artifacts | `tauri_iso_workflow.py` `_workflow_run_dir_required`；對照 `projection.py` L76-95（artifact 層已有 resolve 檢查，run dir 層沒有） | `workflow_read_run_log` 傳 `workflow_run_id="C:/任意資料夾"`（內放偽造 run_log.json） | resolve 後強制位於 `_workflow_run_root()` 之下 | ✅ C1 |
| 3 | Excel file lock | 🟠 中 | `export_plan_csv` 直接 `open("w")`；CSV 被 Excel 開啟時 Windows 丟 `PermissionError`，現在是裸 traceback 進 stderr，前端顯示原始錯誤 | `tauri_iso_workflow.py` `export_plan_csv` L714-717 | Excel 開啟舊匯出檔，再按匯出到同路徑 | tmp+`os.replace` + 捕 PermissionError/winerror 32 → 中文訊息含路徑 | ✅ C2 |
| 4 | replay 寫入副作用 | 🔴 高 | replay + `--include-auto-side-effects` 仍會執行 auto 類（含 `may_write_page_pdfs`=寫使用者資料夾拆頁、`spawns_worker`=重跑 OCR）；guarded 三項已硬封鎖（policy L107-111 已驗），但 auto 在 replay 的語意容易被誤會成「全唯讀」 | `policy.py` SideEffectGate、`executor.replay_workflow` | `replay --run <id> --include-auto-side-effects` 對 combine-pdf 輸入 | 不改行為（拆頁本是預期功能）；C1 加一條測試固化「預設 replay 零寫入」+ 文件明示 include-auto 的語意 | ✅ C1（測試+文件） |
| 5 | 前端意外傳 allow/confirm | 🔴 高 | 型別上 `IsoWorkflowRequest` 有這兩欄位（後端 schema 需要）；任何人寫 `invokeJson("run_iso_workflow", {...spread 大物件})` 就可能把它們帶上去 | `isoWorkflow.ts`（interface 在、helpers 刻意不收）；未來新 helper 是風險點 | 新增一個把整個 state spread 進 request 的呼叫 | C1 靜態守門：兩字串只准出現在 interface 區塊；review 規則寫進 §9 | ✅ C1 |
| 6 | slider / useEffect 觸發 OCR | 🔴 高 | B8 的 overlay 是隨 state 重算的 useMemo，若有人把「overlay 變更」接上 useEffect 自動驗證，ROI 滑桿一拖就是一連串 workflow_run；歷史上 ROI freeze 災難就是這型 | `IsoBoard.tsx` overlay memo、`EngineerView.tsx` 驗證鈕、`WorkflowInspector.tsx` | 在 useEffect 依賴 overlay 呼叫 run | C1 靜態守門：useEffect 區塊禁 run 字串；C3 防重入加固 | ✅ C1+C3 |
| 7 | Tauri dev port 衝突 | 🟡 低 | `vite.config.ts` 已 `strictPort: true`（已驗 L9-10），第二個 dev 實例會直接 fail-fast——殘餘風險只剩殭屍 vite 佔 1420 時錯誤訊息不直觀 | `vite.config.ts` | 開兩個 `npm run dev` | 不改碼；§9 記 workaround（`netstat -ano | findstr 1420` → kill） | ❌ 記錄即可 |
| 8 | Windows 中文/空白路徑 | 🟠 中 | repo 路徑本身含中文；fixture 多在 ASCII tmp，中文+空白資料夾未被系統性覆蓋；subprocess cwd、`utf-8-sig`、JSON 序列化都可能踩 | worker spawn（`cwd=Path.cwd()`）、`export_plan_csv`、projection 路徑拼接 | 在 `tmp/測試 資料夾/` 跑全流程 | C1 `test_chinese_and_space_paths` 固化 | ✅ C1 |
| 9 | 大型 PDF 壓力 | 🟠 中 | `tauri_iso_worker._write_progress` 每頁全量改寫 job.json（含累積 rows）→ O(n²) 寫入；500 頁時 job.json 反覆重寫 + 前端輪詢讀大檔；64MB artifact 上限可能被 rows 撞到 | `tauri_iso_worker.py` L90、`context.py` MAX_ARTIFACT_BYTES | 生成 300+ 頁 PDF 跑 batch detect | C1 先放 60 頁哨兵測試（120s 上限）；真正分頁寫入優化留 D 期（不要在 C 動 worker） | ✅ C1（哨兵）；優化 ❌ |
| 10 | 節點畫布讓 guarded 變快捷 | 🔴 高（預防） | 畫布天生鼓勵「點一下就做」；若 enable 切換/右鍵執行進畫布，B10 的 guarded 防線會被 UX 繞過 | C4 的 `WorkflowCanvas.tsx`（未來 D 期編輯功能） | n/a（設計期防範） | C4 契約五條寫死：唯讀、零執行 handler、鎖定視覺、側欄唯讀、D 期編輯需全名確認+副本另存 | ✅ C4（契約） |

## 8. 測試矩陣（每 phase 收尾跑對應列；C5 跑全部）

| 層 | 命令 | C1 | C2 | C3 | C4 | C5 |
|---|---|---|---|---|---|---|
| 防污染回歸 | `pytest tests\test_iso_workflow_pollution.py -q` | ✅ | ✅ | — | — | ✅ |
| 前端安全契約（靜態） | `pytest tests\test_frontend_safety_contract.py -q` | ✅ | — | ✅ | ✅ | ✅ |
| Workflow 引擎全套 | `pytest tests\test_iso_workflow_engine.py tests\test_iso_workflow_policy.py tests\test_iso_workflow_nodes.py tests\test_iso_workflow_job.py tests\test_iso_workflow_projection.py tests\test_iso_workflow_apply_safety.py tests\test_iso_workflow_cli.py -q` | ✅ | ✅ | — | — | ✅ |
| Backend actions | `pytest tests\test_tauri_iso_workflow.py -q` | ✅ | ✅ | — | — | ✅ |
| Parity | `pytest tests\test_iso_workflow_parity.py -q`（C5 加 `parity-history`） | ✅ | — | — | — | ✅ |
| 前端型別/建置 | `cd frontend\tauri-spike; npx tsc --noEmit; npm run build` | — | ✅ | ✅ | ✅ | ✅ |
| 前端單元 | `npm run test:unit` | — | — | ✅ | ✅ | ✅ |
| Real sample（optional，樣本在才跑） | `cli parity --inputs-json …\poc_inputs.json` | — | — | — | — | ✅ |
| 人工煙測（每 phase 至多一次） | 截圖/操作記錄 | — | — | 1 次 | 1 次 | — |

無 pytest 環境：以 `python -m unittest tests.<module> -v` 跑同名模組（測試皆為 unittest.TestCase）。

## 9. 禁止事項（C 期全程有效）

1. 不恢復 apply 前自動 export CSV；`apply_rename_record.csv` 永遠只進 runtime artifacts。
2. safe mode / replay 預設不得寫使用者工作資料夾（顯式 split 拆頁除外——那是功能本體且只在 run 模式）。
3. `writes_csv` / `renames_files` / `writes_profile` 不得離開 GUARDED 與 REPLAY_HARD_BLOCKED。
4. 前端不得出現 `workflow_allow` / `workflow_confirm` 的一般 UI 路徑（interface 定義除外）；不得新增任何在 useEffect/onChange 觸發 `workflow_run` / OCR 的程式碼。
5. 畫布唯讀：零執行 handler、零 graph 寫回；違者整 phase 重做。
6. 不動一鍵執行路徑（`AutopilotView` 行為零變更）；不動 PyQt legacy；不碰 `.qwen/`；不用 `git add -A`。
7. 不大改架構：engine 公開 API 凍結；新能力一律 append-only（新檔案、新 action、dispatcher 尾端）。
8. 人工測試上限：C3/C4 各一次煙測；其餘一律自動化。
9. 環境註記：Linux 沙箱掛載視圖可能對最近寫入檔案顯示尾端截斷、git 可能報 `improper chunk offset`（commit-graph 視圖假象）——Windows 端以 `git fsck --connectivity-only` 確認即可；沙箱讀真內容用 `git show <ref>:<path>`。Windows 端若真有 chunk 錯誤：刪 `.git\objects\info\commit-graph` 後 `git commit-graph write --reachable`。

## 10. 給 Codex 的開工指令（照抄執行）

```text
請讀 docs/iso_pdf_workflow_c_phase_plan_2026-06-10.md（本文件），它是 C 期唯一 active 施工書，取代前篇 B 期文件的停工令。

Pre-flight（不寫碼）：
1. cd C:\Users\a0976\Documents\GitHub\桌面輔助系統
2. git fsck --connectivity-only   # 若報 commit-graph chunk 錯誤：del .git\objects\info\commit-graph 後 git commit-graph write --reachable
3. git status --short --branch；git log --oneline -3   # 期望 tip=4b6bb05、工作樹乾淨（.qwen/ 除外，永不 stage）
4. git switch codex/tauri-react-spike && git pull --ff-only
5. git switch -c codex/iso-workflow-c
6. git add docs/iso_pdf_workflow_c_phase_plan_2026-06-10.md && git commit -m "docs(iso-workflow): add c phase plan (C0)" && git push -u origin codex/iso-workflow-c

然後照 C1→C2→C3→C4→C5 順序施工：
- 每 phase 一個 commit + push，用各 phase 給定的 commit message；結束先跑該 phase 測試命令全綠 + git diff --stat 不越界。
- C1、C4 是可停下交接的 checkpoint。
- C1 必含兩個後端修補：_workflow_run_dir_required 限制在 run root 之下；防污染測試 10 次 safe run 零 CSV。
- C2 把手動匯出預設改到 .runtime/exports/iso/（保留時間戳、retention 50、Excel 鎖檔中文錯誤）；使用者明示 export_path 永遠優先。
- C4 npm install @xyflow/react 失敗就停下回報，不准手寫 canvas；畫布唯讀，guarded 節點紅鎖灰底，零執行 handler。
- C5 跑 real sample parity（C:\Users\a0976\Downloads\t）：equal → 留檔為第一筆換軌證據；violation → 停工，把 report 原文寫進回報，不要自行修改任一側讓它變綠。
- 遇到邊界不明：停下，寫短報告（現況/選項/建議），不要自行擴大範圍。絕不做 D 期內容：不改一鍵執行路徑、不做畫布編輯、不做 shadow run。
- C5 完成後：merge --no-ff 回 codex/tauri-react-spike、打 tag iso-workflow-c-v1、push、停工回報（檔案清單、命令輸出、parity 結果原文、build 體積增幅、限制與風險）。
```

---

## 11. Codex C 期完工 Postscript（2026-06-10）

> 本節是實際施工履歷；上方 C0-C5 仍是任務契約。若下一輪規劃 D 期，請以本節作為已完成事實與殘留風險來源。

### 11.1 已完成 commit

| Phase | Commit | 內容 |
|---|---|---|
| C0 | `196e9b1 docs(iso-workflow): add c phase plan (C0)` | 新增 C phase active 施工書。 |
| C1 | `5ab3465 test(iso-workflow): add anti-pollution regression suite and run dir guard (C1)` | 防污染測試、run_dir escape guard、frontend safety static tests。 |
| C2 | `20aebe3 feat(iso-workflow): route manual csv exports to runtime exports dir with retention (C2)` | 手動 CSV 匯出預設改到 `.runtime/exports/iso/`、retention 50、Excel lock 中文錯誤。 |
| C3 | `30cdac8 fix(iso-workflow): lift workflow job state to survive view switches (C3)` | workflow job 狀態提升到 `IsoBoard`，切 tab 不遺失執行中狀態。 |
| C4 | `d77ee93 feat(iso-workflow): readonly react-flow canvas with guarded lock language (C4)` | `@xyflow/react` 唯讀畫布、guarded lock 視覺語言、靜態防爆契約。 |
| C5 | `02a6747 feat(iso-workflow): persist parity evidence and define switchover gate (C5)` | parity report 持久化、`parity-history` CLI、唯讀 Tauri history action、Inspector「換軌守門」。 |

### 11.2 C5 real sample parity

已用 `C:\Users\a0976\Downloads\t` 跑過一次 real sample parity，作為第一筆換軌證據：

```text
command:
python -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\poc_inputs.json --json

result:
equal: true
violations: []
acceptable_diff_count: 25
legacy_digest: sha256:e1b8a6dfb31f03af9397656f19502e768539d42231dae1f1a33930bae55e3841
workflow_digest: sha256:e1b8a6dfb31f03af9397656f19502e768539d42231dae1f1a33930bae55e3841
report_path: C:\Users\a0976\Documents\GitHub\桌面輔助系統\.runtime\runs\parity\20260610_163537_10af21\report.json
```

`parity-history --json` 已可列出該筆：

```text
report_count: 1
equal: true
violation_count: 0
acceptable_diff_count: 25
created_at: 2026-06-10T16:35:37
inputs_digest: sha256:0796c5efa2fc4c0e5d695f554cc0f3f864d273b3f3d6e77f0e97d9f2f02c4ef4
```

### 11.3 已跑過的驗證

```powershell
python -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py tests\test_tauri_iso_workflow.py -q
python -m pytest tests\test_iso_workflow_engine.py tests\test_iso_workflow_policy.py tests\test_iso_workflow_job.py tests\test_iso_workflow_projection.py tests\test_iso_workflow_parity.py tests\test_iso_workflow_parity_history.py -q
cd frontend\tauri-spike
npx tsc --noEmit
npm run build
npm run test:unit
python -m launcher.plugins.iso_tools.workflow.cli parity-history --json
```

### 11.4 已知殘留與 D 期 gate

- full `python -m pytest tests -q` 曾跑出 `439 passed, 2 failed`。兩個 failure 都在 `tests/test_smoke.py`，原因是舊 smoke 仍期待 `App.tsx` 中已不存在的 legacy 字串；非 C 期新增 regression，本期未修。
- `npm run build` 因 React Flow 引入後出現 Vite chunk `>500 kB` warning；C4 已記錄 gzip JS 約 `95.15 kB -> 154.41 kB (+59.26 kB)`，C5 最新 build 約 `154.92 kB`。
- D 期換軌 gate 不變：最近 5 筆 parity 全 equal、至少 2 筆 real sample、C1 防污染套件連續綠、shadow run 設計書完成。未達成前不得改 `AutopilotView` 一鍵執行路徑。
