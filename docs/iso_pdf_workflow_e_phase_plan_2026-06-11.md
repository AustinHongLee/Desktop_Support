# ISO PDF Node Workflow E Phase 施工書（安全換軌：workflow-backed 一鍵）

> Date: 2026-06-11
> Base: `codex/tauri-react-spike` @ `750a32d`（merge(iso-workflow): complete D phase；tag `iso-workflow-d-v1`）
> 前篇：`docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md`（含 D5 完工 postscript 與 gate 快照，本文件以其為事實來源）
> 本文件是 E 期唯一 active 施工入口。引用的函式/行號都對照 `750a32d` 實碼驗證過。
> 施工分支：`codex/iso-workflow-e`。實驗樣本：`C:\Users\a0976\Downloads\t`。
> E 期範圍一句話：**一鍵主流程可在 operator gate + feature flag 下改由 workflow engine 產生 plan，legacy 隨時可退，mismatch 會擋，apply 安全不變。** 不做畫布、不做 UI 重設計、不做下一期展望。

---

## 1. E 期總結論：可以開工，前置條件如下

**可以開工。** 唯一前置 = **E0 先補第 5 筆 parity，讓 gate 轉 ready**。

裁決理由（對應任務書第 7 點）：

- 現況（D5 postscript gate 快照）：window 4 筆全 equal、real=3（`recent_all_equal` unmet：4/5；`real_samples` met；`shadow_design` met；`pollution_suite` 手動 attest）。
- **要先補**，因為：(a) E2 要做「enable 換軌時後端強制驗 gate ready」——gate 不 ready 就無法對 enable 路徑做真實的成功測試，只能測拒絕分支；(b) 補一筆的成本是幾分鐘（一條 CLI 命令），而 gate ready 是 E 期一切的合法性來源，沒有理由帶著 not ready 開工；(c) D5 postscript 自己寫明「E 期若要開工，至少要先補足最近 5 筆 parity window」。
- 補法（E0 步驟，operator 在 Windows 跑）：
  ```powershell
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\poc_inputs.json --sample-kind real --json
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli gate --json   # 期望 recent_all_equal met、ready 視 G3 attest 而定
  ```
  補完後 window = 5 筆全 equal、real ≥ 4 → G1/G2/G4 met；G3（pollution suite）在 E0 跑一次套件即 attest。若補的這筆出現 violation → **E 期暫停開工**，violation 報告原文交回裁決（這代表兩路徑在真樣本上有實質分歧，換軌前必須先解）。

## 2. E 期 Definition of Done（9/10 工程標準）

E 期完成 = 以下每一條都可被命令或測試客觀驗證，缺一不可：

1. **換軌可用**：operator 在節點式分頁開啟 workflow primary 後，一鍵按鈕實際由 workflow engine（鎖定圖 `iso_pdf_one_click.workflow.json`）產生 plan，review/apply 流程與 legacy 完全相同。
2. **預設安全**：engine flag 檔不存在時，一鍵行為與 `750a32d` 位元組級等價（前端 DOM、後端 action 序列皆不變）；全部既有測試零修改通過。
3. **Operator gate 強制**：enable 換軌的後端 action 在 gate not ready 時拒絕（測試覆蓋）；enable 時把 gate 快照 + 圖 hash 寫進 flag 檔與 audit log。
4. **Legacy fallback 三層**：(a) 隨時可手動切回（disable 永遠允許）；(b) workflow 一鍵失敗時 UI 提供「改用傳統路徑重跑」一鍵按鈕；(c) 連續 2 次 workflow 一鍵失敗 → 後端 lazy 自動回退 legacy + audit + UI 橫幅。
5. **No silent change**：一鍵頁顯示目前引擎 chip（傳統路徑／節點路徑·驗證中）；每次引擎切換（手動與自動）都進 `engine_audit.jsonl`；workflow 一鍵的 run log 與 iso run log 雙軌可追。
6. **Apply 安全不變**：rename 仍走既有 `apply` action（`_validate_operations` + B11 record artifact + 既有確認 UI）；workflow 只改變 plan 的產生者。`renames_files`/`writes_profile`/`writes_csv` 的 guarded 與 replay 硬封鎖零變化。
7. **資料契約被測試釘死**：前端消費的 plan 欄位清單寫成白名單測試，legacy result 與 workflow projection 都必須逐欄滿足（§3）。
8. **Failure mode 全覆蓋**：§4 表中 10 種情境各有偵測點、使用者下一步、自動化測試。
9. **驗證全綠**：full pytest 0 failed、`npx tsc --noEmit`、`npm run build`、`npm run test:unit`、pollution + safety contract、real sample 雙引擎實測各一次（E5 記錄原文）。
10. **文件記錄可進入狀態**：本文件 postscript 含 gate 快照、雙引擎實測輸出、「workflow primary 可進入/不可進入」的明確結論與開關手冊。

**Deferred 且不影響 9/10 的項目**（依任務書規則 3 逐條說明）：

| 項目 | 為何不影響 E 期完成度 |
|---|---|
| 移除 legacy 路徑 | legacy **就是** rollback 結構本體（DoD 4）。移除是換軌穩定數週後的清理工作，保留它是 9/10 的要求而非欠缺 |
| 自動 shadow / 每次 primary 跑後自動 parity | 換軌合法性由 gate（5 筆 real equal）+ E5 雙引擎實測保證；primary 模式每次再跑 legacy = 永久雙倍 OCR，是成本錯誤而非完整度缺口。取而代之的是每次 primary run 的 sanity guard（§3.3）+ 手動 shadow 工具仍在 |
| parity normalize v3 | 現行 normalize 已被 5 筆 real equal 驗證足夠判定此樣本族群；E 期 primary 不逐次跑 parity，normalize 版本不在關鍵路徑上 |
| 可編輯畫布 / params overlay 編輯 | 與換軌無依賴關係；換軌用的是鎖定圖（hash 釘死），可編輯性反而是風險 |


---

## 3. 一鍵換軌資料契約（任務書第 8 點）

### 3.1 兩側 schema 與消費點（對照 `750a32d` 實碼）

```text
legacy 一鍵：
  IsoBoard.runOneClick (L788 setOneClickStage("running"))
    → startIsoBatchDetect → batchJob 輪詢 (L762 effect, 唯讀)
    → terminal completed → job.result（= tauri_iso_worker._result_payload，action="batch_detect_result"）
    → L584 setPlan(result) → L817 done / L830 review → L835 applying → applyIsoPlan(selected rows)

workflow primary（E3 之後，flag 開啟時）：
  IsoBoard.runOneClick（同一顆按鈕、同一 onClick）
    → runIsoOneClickWorkflow()（新 helper；後端 workflow_run + one_click marker）
    → workflow job 輪詢（唯讀 status；node 進度映射 §3.4）
    → terminal completed → loadIsoWorkflowPlanFromRun(run_id)（B5 投影 + E1 sanity guard）
    → 同一個 setPlan(projection) → 之後 review/apply 與 legacy 共用同一條路，零分叉
```

換軌的全部本質 = **「setPlan 的供應者可替換」**。L584 之後的程式碼（review 表、Pilot、apply、CSV、run log drawer）一行都不改。

### 3.2 消費欄位白名單（E1 的契約測試內容，兩側都必須提供）

頂層：`schema_version`、`action`、`created_at`、`source{kind, work_folder, combine_pdf, page_folder, pdf_count, iso_list, sheet_name, headers, serial_col, line_col, record_count, pattern, detect_serials, confidence_threshold, serial_region, drawing_region, profile}`、`summary{total, ready, warn, blocked, …}`、`steps[]`、`rows[]`、`issues[]`、`pilot_results[]`。
rows 每列：`id, page, source_path, source_name, serial, line_no, new_name, target_path, status, selected, confidence, vision_message, note`（= `IsoPlanRow`，isoWorkflow.ts L296-310）。
pilot 每項：`id, stage, status, user_text, engineer_detail, metrics, auto_fix, manual_hint, blocks_apply, issue_codes`（P01-P15 凍結；v2 附加欄位 optional）。
投影側已知差異要在 E1 處理：`action` 值是 `"workflow_plan_from_run"`（前端 union 已含）；`provenance` 是投影側多出的欄位（消費端忽略即可，白名單不要求 legacy 提供）。

### 3.3 sanity guard（primary 模式每次 run 的便宜不變量，E1 實作 `validate_one_click_plan()`）

1. run status 必須 `completed`（`completed_with_blocked` 一律視為失敗——one_click 圖內**沒有任何 guarded 節點**，出現 blocked = 圖被竄改）。
2. `rows` 非空且 `len(rows) == source.pdf_count`。
3. selected 列的 `target_path` 無重複、無空值。
4. `summary` 計數與 rows 逐列統計一致。
5. `pilot_results` 存在且含 `P01`。
任一不變量失敗 → 投影 action 回錯誤（含具體哪條），前端按 workflow 失敗處理（fallback 路徑），**絕不把可疑 plan 餵給 review/apply**。

### 3.4 進度映射（使用者不該看見工程概念，任務書第 10 點）

| workflow node | 一鍵進度文案 | 進度值 |
|---|---|---|
| `split` | 「拆頁中…」 | 節點序/總數 |
| `load_table` | 「讀取 ISO 清單…」 | 同上 |
| `batch_detect` | 「辨識流水號…（n/m 頁）」 | 轉發內層 `current_node_percent` |
| `pilot` | 「自動檢查中…」 | 同上 |
引擎 chip 文案：legacy=「傳統路徑」、primary=「節點路徑（驗證中）」；除 chip 與失敗卡外，一鍵頁不出現任何 workflow/graph/node 字眼。

## 4. Failure mode 對照表（任務書第 9 點；E1-E4 落實，E4 收尾驗證）

| # | 情境 | 偵測點 | 系統行為 | 使用者看到的下一步 | 測試 |
|---|---|---|---|---|---|
| 1 | workflow run failed（node 失敗） | workflow job state=failed | 不 setPlan；記 run log；breaker 計數+1 | FailureCard：失敗節點的人話說明（§E4 對照表）+「改用傳統路徑重跑」按鈕 | E3/E4 |
| 2 | parity mismatch | gate（enable 時）；手動 shadow（運行期抽查） | enable 被拒 / report 留檔 exit 6 | 節點式 gate 面板紅色條件 + report 路徑 | E2 |
| 3 | timeout | workflow job runner timeout（one_click 預設 1800s）→ failed | 同 #1 + cancel 內層 iso job（既有鏈） | 同 #1，文案註明逾時 | E4 |
| 4 | 使用者取消 | 一鍵取消按鈕 → primary 時映射 `cancelIsoWorkflowJob` | job cancelled；不計入 breaker | 「已取消，保留已完成進度」（沿用既有文案） | E3 |
| 5 | locked CSV（匯出/記錄檔被 Excel 開啟） | `export_plan_csv` / B11 record 寫入 PermissionError | C2 已包匯出；E4 把 apply record 寫入包成同款中文錯誤（apply 本體成功不受影響，record 失敗降級為警示） | 「記錄檔被佔用：<path>，更名已完成，記錄稍後補寫」 | E4 |
| 6 | locked PDF（更名目標被開啟） | `_apply_operations` PermissionError | E4 wrap：明示哪個檔案鎖住、已完成幾筆、未動幾筆 | 「<file> 正被開啟，關閉後按『重試剩餘』」（重試=再按 apply，既有冪等：已改名列不再選中） | E4 |
| 7 | xlsx 載入錯誤 | `load_table` 節點失敗（`_resolve_iso_records` 中文 raise） | 同 #1 | 「ISO 清單讀取失敗：<原因>。請檢查檔案後重試」+ fallback 按鈕 | E4 |
| 8 | node side effect blocked | run status=completed_with_blocked | sanity guard 規則 1 → 視為失敗 + audit 記「圖完整性異常」 | 同 #1 + 提示聯繫工程模式 | E1/E4 |
| 9 | 連續失敗 | `workflow_one_click_engine` 讀取時 lazy 掃最近 2 筆 one_click 標記 run | 自動回退 legacy + audit `auto_revert` | 下次按一鍵：橫幅「已自動切回傳統路徑（連續失敗保護）」+ 正常跑 legacy | E2/E4 |
| 10 | 舊 v1 parity report / unknown | gate G2 不計 unknown（D2 既有） | 無新行為 | gate 面板 unknown chip（D3 既有） | 回歸 |


---

## 5. Phase 拆分（E0-E5）

> 通則：每 phase 一 commit + push；測試命令全綠 + `git diff --stat` 不越界才進下一 phase。E1/E2 backend 🟢 checkpoint。**不能碰的區域（全期）**：`applyIsoPlan`/`_apply_operations` 的確認與安全語意、工作台與調校分頁行為、policy 三集合、Pilot P01-P15、PyQt legacy、`.qwen/`、normalize 規則、可編輯畫布。

### E0 — Gate 補齊 + 施工書入庫（operator + docs）

- **目標**：第 5 筆 real parity 入窗、gate 條件 G1-G2-G4 全 met、G3 以一次套件執行 attest；施工書 commit。
- **修改檔案**：本文件入庫；無程式碼。
- **步驟**：§1 的兩條 CLI + `python -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q`；gate JSON 快照貼進本文件 E0 註記（append 一小節）。
- **禁止**：違規 parity（violation）時不准開工 E1。
- **驗收**：`gate --json` 顯示 `recent_all_equal: met`、`real_samples: met`；快照入文件。
- **Rollback**：docs only。
- **Commit**：`docs(iso-workflow): add e phase plan with gate readiness (E0)`

### E1 — 換軌資料契約固化（backend，零行為變更）🟢

- **目標**：把 §3 全部變成程式與測試：one_click 鎖定圖、sanity guard、消費欄位契約測試。
- **修改檔案**：
  - 新增 `launcher/plugins/iso_tools/workflow/workflows/iso_pdf_one_click.workflow.json`（`split → load_table → batch_detect → pilot` 四節點；inputs 同 safe POC 的 11 欄；`metadata.locked=true`；**圖內零 guarded 節點**、零 export、零 apply）
  - 新增 `launcher/plugins/iso_tools/workflow/one_click_guard.py`（`validate_one_click_plan(run_log, projection) -> list[str]`，§3.3 五條不變量，純函式）
  - 修改 `launcher/plugins/iso_tools/workflow/projection.py`（`plan_from_run(run_dir, *, one_click_guard=False)`：guard=true 時跑五條，失敗 raise ValueError 列明哪條）
  - 新增 `tests/test_iso_one_click_contract.py`：(a) 圖驗證（validate 0 error、locked、零 guarded、`graph_content_hash` 穩定值寫進測試）；(b) 欄位白名單測試——白名單寫死在測試檔，分別對 legacy fixture（in-process `run_job` 的 `job.result`）與投影輸出逐欄斷言存在/型別；(c) sanity guard 五條各一個失敗注入測試；(d) 前端消費面掃描：grep `IsoBoard.tsx`/`AutopilotView.tsx` 對 `plan.`/`row.` 的取值不超出白名單（超出 = 測試紅，提醒同步契約）。
- **禁止**：不動 safe POC json；不動既有投影行為（guard 是 opt-in 參數）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_one_click_contract.py tests\test_iso_workflow_projection.py tests\test_iso_workflow_nodes.py -q
  ```
- **驗收**：契約測試全綠；one_click 圖 hash 值記進 commit message。
- **Rollback**：純新增；revert 無影響。
- **Commit**：`feat(iso-workflow): one-click workflow contract and sanity guard (E1)`
- 🟢 可停下交接。

### E2 — Engine switch 後端（operator gate + audit + breaker）🟢

- **目標**：引擎切換成為被 gate 守住、可審計、會自動回退的後端事實。
- **修改檔案**：
  - 修改 `launcher/app/tauri_iso_workflow.py` append：
    - `_one_click_engine_path() = runtime_root()/".runtime"/"flags"/"iso-one-click-engine.json"`
    - `workflow_one_click_engine_action`（唯讀 + lazy breaker）：讀 flag 檔（不存在 → `{engine:"legacy"}`）；engine=workflow 時掃描 workflow job root 中最近 2 筆帶 `one_click` 標記的 job——兩筆皆 failed → 改寫 flag 檔回 legacy、append audit `{"event":"auto_revert","reason":"consecutive_failures",...}`、回傳 `auto_reverted: true`。
    - `workflow_set_one_click_engine_action`：enable（→workflow）時後端呼叫 gate 評估，`ready=false` → raise（訊息含未達成條件）；ready → 寫 flag 檔 `{engine:"workflow", enabled_at, gate_snapshot, graph_hash(one_click 圖), schema_version:1}` + audit `{"event":"enable",...}`。disable（→legacy）永遠允許 + audit。
    - audit 檔：`runtime_root()/.runtime/runs/engine_audit.jsonl`（append-only，一行一事件）。
    - `workflow_run` 接受 request `workflow` dict 內 `one_click: true` 標記：強制 workflow_path=one_click 圖、驗 `graph_content_hash == flag 檔記錄的 hash`（不符 → raise「一鍵圖已被修改，請重新啟用換軌」）、強制 allow/confirm 空、runner request.json 帶 `one_click` 標記（供 breaker 掃描）。
  - 新增 `tests/test_iso_one_click_engine.py`：gate not ready enable 拒絕（synthetic 注入）；ready enable 成功 + flag 檔欄位 + audit 行；disable 永遠成功；hash 不符拒跑；synthetic 連續 2 failed → 讀取時 auto-revert + audit + `auto_reverted` 回傳；cancelled 不計入 breaker。
- **禁止**：flag 檔路徑固定（無使用者輸入）；不做 UI；audit 不可刪改（只 append）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_one_click_engine.py tests\test_tauri_iso_workflow.py tests\test_iso_workflow_job.py tests\test_iso_workflow_gate.py -q
  ```
- **驗收**：上列全綠；真環境 `workflow_set_one_click_engine` enable 成功（E0 已 ready）後 disable 回 legacy，audit 兩行可見。
- **Rollback**：append-only；revert 後殘留 flag/audit 檔為惰性資料；刪 flag 檔 = 回 legacy（這本身就是緊急 rollback 手段，寫進手冊）。
- **Commit**：`feat(iso-workflow): gated one-click engine switch with audit and breaker (E2)`
- 🟢 可停下交接。

### E3 — 一鍵前端換軌（frontend 核心）

- **目標**：同一顆一鍵按鈕在 engine=workflow 時走 workflow 路徑，產出餵進同一個 `setPlan`（IsoBoard L584 同位），review/apply 零分叉；UI 有引擎 chip 與 fallback 按鈕。
- **修改檔案**：
  - `frontend/tauri-spike/src/isoWorkflow.ts` append：`loadIsoOneClickEngine()`、`setIsoOneClickEngine(engine)`、`runIsoOneClickWorkflow(inputs)`（action workflow_run + `workflow:{one_click:true}` 標記；簽名無 allow/confirm）、`loadIsoWorkflowPlanFromRun(runId, {oneClickGuard:true})` 參數透傳。
  - `frontend/tauri-spike/src/iso/IsoBoard.tsx`：`runOneClick` 開頭 `const engine = await loadIsoOneClickEngine()`（**click-time 讀取**，不輪詢、不 useEffect）；`engine.auto_reverted` → 設定橫幅訊息；workflow 分支：跑 → 輪詢（沿用 C3 的 workflow job state 模式）→ 終態 completed → 投影（guard on）→ `setPlan(projection)` → 既有 stage 機轉；failed/timeout/guard 失敗 → `setOneClickFailure` 變體（§4 文案）+ `fallbackToLegacy()` 按鈕 handler（onClick 重跑 legacy 分支，一次性，不改 flag）；取消按鈕在 workflow 分支映射 `cancelIsoWorkflowJob`；進度依 §3.4 映射。
  - `frontend/tauri-spike/src/iso/AutopilotView.tsx`：header 引擎 chip（props 傳入；legacy 時不渲染任何新元素以外的變化——chip 在 legacy 也顯示「傳統路徑」？**裁決：flag 檔不存在時不顯示 chip**，完全零變化；存在（含 legacy 值）才顯示，因為這代表 operator 已介入過）；FailureCard 增 next-step 按鈕 slot（props）。
  - `tests/test_frontend_safety_contract.py` append：`runIsoOneClickWorkflow(` 呼叫點恰 1 處（runOneClick 鏈內）且不在 useEffect；`setIsoOneClickEngine(` 呼叫點恰 1 處（節點式 gate 面板）；`workflow_allow|workflow_confirm` 規則不變適用新 helper。
  - `frontend/tauri-spike/src/iso/WorkflowInspector.tsx`：gate 面板加引擎開關（enable 按鈕附確認對話框，顯示 gate 快照摘要；disable 一鍵即生效）。
- **禁止**：不動 L584 之後的 review/apply 程式；不在 useEffect 讀 engine；不自動 fallback（必須使用者按）；工作台/調校零 diff。
- **測試命令**：
  ```powershell
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit
  & .venv\Scripts\python.exe -m pytest tests\test_frontend_safety_contract.py -q
  ```
- **驗收**：tsc/build/vitest/守門綠；flag 檔不存在時 `git diff` 之外一鍵頁渲染等價（手動煙測：無 flag 跑一次 legacy 一鍵確認無 chip 無新元素）。
- **Rollback**：revert 即回 legacy-only 前端；後端 E2 能力保留（CLI/手動可用）。緊急情況：刪 flag 檔即全域回 legacy，前端無需改版。
- **Commit**：`feat(iso): one-click runs on workflow engine behind operator gate (E3)`

### E4 — Failure modes 落地 + UX 收尾（前後端小修）

- **目標**：§4 表 10 條全數有實作與測試；錯誤都有人話與下一步。
- **修改檔案**：`tauri_iso_workflow.py`（apply 的 PermissionError wrap：鎖定 PDF 訊息含檔名與已完成筆數；B11 record 寫入失敗降級為 response 警示欄位 `record_warning` 而非整體失敗）；`IsoBoard.tsx`/`AutopilotView.tsx`（failed_node→人話對照：split=PDF 問題、load_table=ISO 清單問題、batch_detect=辨識問題、pilot=檢查問題；橫幅與「重試剩餘」文案）；one_click workflow timeout param 1800s；新增 `tests/test_iso_one_click_failures.py`（鎖檔模擬 monkeypatch、completed_with_blocked 注入、timeout→cancel 鏈、breaker E2E：2 failed→讀 engine→auto_reverted→audit）。
- **禁止**：不改 `_apply_operations` 的執行語意（只包錯誤訊息）；不新增重試自動化（重試=使用者再按）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_one_click_failures.py tests\test_iso_one_click_engine.py tests\test_tauri_iso_workflow.py tests\test_iso_workflow_pollution.py -q
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build
  ```
- **驗收**：10 條 failure 各對應至少一測試；手動煙測一次（開 flag → workflow 一鍵 → 中途取消 → 重跑 → 完成 → apply 樣本副本）。
- **Rollback**：錯誤包裝與 UI 文案皆增量；revert 不影響 E1-E3。
- **Commit**：`feat(iso): one-click failure handling and friendly errors (E4)`

### E5 — 雙引擎真機驗證 + 合流（operator + docs）

- **目標**：同一真樣本雙引擎實測等價、全矩陣綠、文件給出「workflow primary 可進入」結論。
- **Operator 步驟**（輸出原文進 postscript）：
  ```powershell
  # 1) legacy 基準：無 flag 跑一鍵（樣本副本資料夾），記 summary
  # 2) 節點式分頁 enable workflow primary（gate ready）
  # 3) workflow 一鍵同樣本副本，記 summary；兩者 rows/summary 對照（可再跑一筆 shadow/CLI parity 留證）
  # 4) 測試 fallback：手動 disable → 再跑一次 legacy 確認回退乾淨
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli gate --json
  & .venv\Scripts\python.exe -m pytest tests -q          # full
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit
  ```
- **修改檔案**：本文件 append「E 期完工 Postscript」（commit 清單、雙引擎輸出、gate 快照、audit 摘錄、開關手冊：enable/disable/緊急刪 flag 檔、殘留）。
- **驗收**：full pytest 0 failed；雙引擎 summary 等價；fallback 實測通過；postscript 完整。
- **Merge/tag**：`git merge --no-ff codex/iso-workflow-e -m "merge(iso-workflow): complete E phase"` → `git tag -a iso-workflow-e-v1 -m "workflow-backed one-click behind operator gate"` → push → 刪本地分支。
- **Rollback**：docs only；整期 rollback = revert merge 或刪 flag 檔（後者不需動 git）。
- **Commit**：`docs(iso-workflow): record e phase completion and switchover manual (E5)`


---

## 6. 風險表

| # | 風險 | 嚴重度 | Mitigation |
|---|---|---|---|
| 1 | 換軌後 plan 語意飄移（投影欄位缺漏/型別差）讓 review/apply 出錯 | 🔴 | E1 契約測試白名單雙側逐欄釘死 + 前端消費面掃描測試（超出白名單即紅）+ sanity guard 五不變量 |
| 2 | workflow 一鍵把可疑結果餵給 apply | 🔴 | guard 失敗 = 不 setPlan、走失敗卡；one_click 圖零 guarded 節點 + hash 釘死，`completed_with_blocked` 一律失敗 |
| 3 | Silent engine 切換（使用者不知道走哪條） | 🔴 | flag 檔存在才顯示 chip；enable 需 gate + 確認對話框；audit jsonl 全事件；auto-revert 有橫幅 |
| 4 | breaker 誤觸發（取消被當失敗 → 亂回退） | 🟠 | cancelled 不計入 breaker（E2 測試明列）；breaker 只看帶 one_click 標記的 run |
| 5 | breaker 不觸發（失敗 run 標記遺失） | 🟠 | 標記寫在 runner request.json（後端寫入，不信前端）；E4 E2E 測試覆蓋 |
| 6 | gate 被 fixture/舊報告灌水後 enable | 🟠 | D2 既有：G2 只計 real、unknown 不計；enable 時 gate 快照入 audit 可追責 |
| 7 | flag 檔被手動亂改（engine 值/hash 竄改） | 🟠 | 讀取時 schema 驗證，非法值一律視為 legacy + audit `invalid_flag`；hash 不符拒跑 workflow 一鍵 |
| 8 | 鎖檔（PDF/CSV）在 apply 中途中斷留半套 | 🟠 | `_validate_operations` 先驗衝突（既有）；E4 錯誤訊息含已完成/未動筆數；重試走既有冪等（已改名列不再選中） |
| 9 | 雙引擎並存使 run log 來源混淆 | 🟡 | workflow 一鍵同時有 workflow run log + iso run log（worker 既有），projection `provenance` 鏈接兩者；RunLogDrawer 不需改 |
| 10 | E3 前端改動波及 legacy 分支 | 🔴 | flag 不存在 → 分支短路直走既有程式；E3 驗收含「無 flag 渲染等價」煙測 + 全既有測試零修改通過 |

## 7. 最終 merge / tag 策略

```text
branch: codex/iso-workflow-e（自 codex/tauri-react-spike @ 750a32d）
commits: E0 docs → E1 feat → E2 feat → E3 feat → E4 feat → E5 docs（各一，message 如各 phase 給定）
checkpoint: E1、E2 後可停下交接；E3 起前後端耦合，建議連續完成 E3→E4
merge 條件: E5 驗收全過（full pytest 0 failed + 前端三件套 + 雙引擎實測 + postscript）
merge: git switch codex/tauri-react-spike && git merge --no-ff codex/iso-workflow-e -m "merge(iso-workflow): complete E phase"
tag:   git tag -a iso-workflow-e-v1 -m "workflow-backed one-click behind operator gate" && git push origin codex/tauri-react-spike iso-workflow-e-v1
緊急 rollback 階梯（寫進手冊）:
  1) 刪 .runtime/flags/iso-one-click-engine.json → 立即全域回 legacy（不動 git）
  2) revert E3/E4 單 commit → 前端回 legacy-only
  3) revert merge → 整期回退（E1/E2 為純新增，留著無害）
```

## 8. 給 Codex 的照抄施工指令

```text
請讀 docs/iso_pdf_workflow_e_phase_plan_2026-06-11.md（本文件），它是 E 期唯一 active 施工書。

Pre-flight（不寫碼）：
1. cd C:\Users\a0976\Documents\GitHub\桌面輔助系統
2. git fsck --connectivity-only
3. git status --short --branch；git log --oneline -3   # 期望 tip=750a32d、工作樹乾淨（.qwen/ 除外，永不 stage）
4. git switch codex/tauri-react-spike && git pull --ff-only
5. git switch -c codex/iso-workflow-e
6. 執行 E0：CLI 補第 5 筆 real parity → gate --json 確認 recent_all_equal met → 跑 pollution+safety 套件 attest → gate 快照貼進本文件 E0 註記
   ※ 若該筆 parity 出現 violation：停工，report 原文交回，不准進 E1。
7. git add docs/iso_pdf_workflow_e_phase_plan_2026-06-11.md && git commit -m "docs(iso-workflow): add e phase plan with gate readiness (E0)" && git push -u origin codex/iso-workflow-e

然後照 E1→E2→E3→E4→E5 施工：
- 每 phase 一 commit + push，用給定 message；結束跑該 phase 測試命令全綠 + git diff --stat 不越界。
- E1、E2 是可停下交接的 checkpoint；E3、E4 建議連續完成。
- 鐵則：flag 檔不存在時一鍵行為與 750a32d 等價（全部既有測試零修改必須通過）；enable 換軌只能經 gate-enforced action；one_click 圖零 guarded 節點、hash 釘死；completed_with_blocked = 失敗；fallback 必須使用者點擊、不自動；取消不計入 breaker；apply/confirmation/side-effect 安全零變化；不在 useEffect 讀 engine 或觸發任何執行；前端永無 allow/confirm 路徑。
- 不能碰：IsoBoard L584 之後的 review/apply 程式、工作台/調校分頁、policy 三集合、Pilot P01-P15、normalize、PyQt legacy、可編輯畫布。
- E5 雙引擎實測 summary 不等價：停工，輸出原文交回，不准修任一側硬讓它等價。
- 遇到邊界不明：停下寫短報告（現況/選項/建議），不要擴大範圍。本文件沒有寫的下一期內容一律不做。
- E5 完成後：merge --no-ff 回 codex/tauri-react-spike、tag iso-workflow-e-v1、push、停工回報（commit 清單、全矩陣輸出、雙引擎對照、gate 快照、audit 摘錄、開關手冊位置）。
```

## 9. E0 Gate Readiness 記錄（2026-06-11）

E0 已完成，可以進入 E1。執行時使用 `python` 直接呼叫目前環境；未使用 `.venv` 路徑。

### Pre-flight

```text
git fsck --connectivity-only
exit 0；僅列出 dangling objects，無 connectivity failure。

git switch codex/tauri-react-spike
git pull --ff-only
Already up to date.

git switch -c codex/iso-workflow-e
```

### 第 5 筆 Real Parity

使用輸入：`.runtime\temp\d5_real_inputs.json`

```powershell
python -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\d5_real_inputs.json --sample-kind real --json
```

結果摘要：

```json
{
  "schema_version": 2,
  "action": "workflow_parity",
  "trigger": "cli",
  "sample_kind": "real",
  "equal": true,
  "violations": [],
  "acceptable_diff_count": 25,
  "legacy_digest": "sha256:e1b8a6dfb31f03af9397656f19502e768539d42231dae1f1a33930bae55e3841",
  "workflow_digest": "sha256:e1b8a6dfb31f03af9397656f19502e768539d42231dae1f1a33930bae55e3841",
  "report_path": "C:\\Users\\a0976\\Documents\\GitHub\\桌面輔助系統\\.runtime\\runs\\parity\\20260611_083203_a1349a\\report.json"
}
```

### Gate Snapshot

```powershell
python -m launcher.plugins.iso_tools.workflow.cli gate --json
```

Exit code：`0`

```json
{
  "schema_version": 1,
  "action": "workflow_switchover_gate",
  "ready": true,
  "headline": "可進入 E 期換軌評估",
  "evaluated_at": "2026-06-11T08:32:17",
  "conditions": [
    {
      "id": "recent_all_equal",
      "met": true,
      "detail": "已達成"
    },
    {
      "id": "real_samples",
      "met": true,
      "detail": "已達成"
    },
    {
      "id": "pollution_suite",
      "met": null,
      "detail": "python -m pytest tests/test_iso_workflow_pollution.py tests/test_frontend_safety_contract.py -q"
    },
    {
      "id": "shadow_design",
      "met": true,
      "detail": "docs\\iso_pdf_workflow_d_phase_plan_2026-06-10.md"
    }
  ],
  "window_summary": [
    {
      "created_at": "2026-06-11T08:32:03",
      "trigger": "cli",
      "sample_kind": "real",
      "equal": true,
      "violation_count": 0
    },
    {
      "created_at": "2026-06-11T08:01:26",
      "trigger": "cli",
      "sample_kind": "real",
      "equal": true,
      "violation_count": 0
    },
    {
      "created_at": "2026-06-10T17:54:01",
      "trigger": "shadow",
      "sample_kind": "real",
      "equal": true,
      "violation_count": 0
    },
    {
      "created_at": "2026-06-10T17:18:37",
      "trigger": "cli",
      "sample_kind": "real",
      "equal": true,
      "violation_count": 0
    },
    {
      "created_at": "2026-06-10T16:35:37",
      "trigger": "cli",
      "sample_kind": "unknown",
      "equal": true,
      "violation_count": 0
    }
  ]
}
```

### G3 Attest

```powershell
python -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q
13 passed in 3.64s
```

E0 結論：`recent_all_equal=true`、`real_samples=true`、`shadow_design=true`，且 G3 指定套件已綠。E1 可開工。

---

## 10. E 期完工 Postscript（2026-06-11）

結論：E 期已達成「workflow-backed 一鍵」9/10 工程目標。workflow primary 由 operator gate + feature flag 控制；flag 不存在時維持 legacy，一鍵頁只在 flag 存在後顯示引擎 chip；workflow 失敗不會自動 fallback，必須由使用者按「改用傳統路徑重跑」；連續兩次 workflow 一鍵失敗會 lazy auto-revert 到 legacy 並寫 audit。

### Commit 清單

```text
d61e6f4 docs(iso-workflow): add e phase plan with gate readiness (E0)
d917235 feat(iso-workflow): one-click workflow contract and sanity guard (E1)
de33762 feat(iso-workflow): gated one-click engine switch with audit and breaker (E2)
799a069 feat(iso): one-click runs on workflow engine behind operator gate (E3)
79d5644 feat(iso): one-click failure handling and friendly errors (E4)
```

### 驗證矩陣

```text
python -m pytest tests -q
482 passed in 66.24s

cd frontend\tauri-spike
npx tsc --noEmit
exit 0

npm run -s build
vite build OK

npm run -s test:unit
3 passed
```

E4 focused：

```text
python -m pytest tests\test_iso_one_click_failures.py tests\test_iso_one_click_engine.py tests\test_tauri_iso_workflow.py tests\test_iso_workflow_pollution.py -q
43 passed in 5.87s
```

### 雙引擎真樣本 Smoke

樣本來源：`C:\Users\a0976\Downloads\t` 複製到 `.runtime\temp\e5_sample_20260611_091554`，未改動原始資料夾。

報告：`.runtime\temp\e5_dual_engine_report_20260611_091554.json`

```json
{
  "equal": true,
  "legacy_summary": {
    "total": 4,
    "ready": 4,
    "warn": 0,
    "blocked": 0,
    "selected": 4
  },
  "workflow_summary": {
    "total": 4,
    "ready": 4,
    "warn": 0,
    "blocked": 0,
    "selected": 4
  },
  "workflow_run_id": "wf-20260611-091610-c99d21",
  "legacy_job_id": "e5-legacy-20260611_091554",
  "one_click_graph_hash": "sha256:58eb621dfe9dce1edf9066e61f6427018214dc601a6e3408da0ee7869cc652d7"
}
```

Fallback smoke：

```json
{
  "engine": "legacy",
  "enabled": false,
  "fallback_job_state": "completed",
  "fallback_summary": {
    "total": 4,
    "ready": 4,
    "warn": 0,
    "blocked": 0,
    "selected": 4
  }
}
```

### Gate / Audit 摘要

```text
python -m launcher.plugins.iso_tools.workflow.cli gate --json
ready=true
headline=可進入 E 期換軌評估
evaluated_at=2026-06-11T09:17:56
recent_all_equal=true
real_samples=true
shadow_design=true
```

`engine_audit.jsonl` E5 摘要：

```json
{"event":"enable","gate_ready":true,"graph_hash":"sha256:58eb621dfe9dce1edf9066e61f6427018214dc601a6e3408da0ee7869cc652d7","at":"2026-06-11T09:16:09"}
{"event":"disable","engine":"legacy","reason":"e5_smoke_disable","at":"2026-06-11T09:16:26"}
```

目前 flag：

```json
{
  "schema_version": 1,
  "engine": "legacy",
  "reason": "e5_smoke_disable"
}
```

### 開關手冊

啟用 workflow primary：

```powershell
'{"action":"workflow_set_one_click_engine","workflow":{"engine":"workflow"}}' |
  python -m launcher.app.tauri_iso_workflow
```

切回 legacy：

```powershell
'{"action":"workflow_set_one_click_engine","workflow":{"engine":"legacy","reason":"manual_disable"}}' |
  python -m launcher.app.tauri_iso_workflow
```

緊急 rollback：

```powershell
Remove-Item -LiteralPath ".runtime\flags\iso-one-click-engine.json"
```

備註：刪 flag 不會改 git，不會刪 run log；下次一鍵會回到 legacy。若 workflow 一鍵連續兩次失敗，`workflow_one_click_engine` 讀取時會自動寫回 legacy flag 並 append `auto_revert` audit。
