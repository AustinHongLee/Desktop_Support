# ISO PDF Node Workflow D Phase 施工書（Shadow Run + 換軌 Gate 自動化）

> Date: 2026-06-10
> Base: `codex/tauri-react-spike` @ `4780832`（merge(iso-workflow): complete C phase；tag `iso-workflow-c-v1`）
> 前篇：`docs/iso_pdf_workflow_c_phase_plan_2026-06-10.md`（含 §11 Codex C 期完工 Postscript，本文件以其為事實來源）
> 本文件是 D 期唯一 active 施工入口。引用的函式/行號/測試名都對照 `4780832` 實碼驗證過。
> 施工分支：`codex/iso-workflow-d`。實驗樣本：`C:\Users\a0976\Downloads\t`。

---

## 1. 結論：現在能不能進 D 期？

**能，立刻能。** 換軌 gate（5 筆 equal、≥2 real、防污染綠、shadow 設計書）守的是 **E 期「真換軌」**，不是 D 期開工；D 期的本體恰恰是「把 gate 所需的證據機器造出來」。目前 gate 4 條中只有「防污染套件綠」達成、parity 證據只有 1 筆（且無 sample 標記）、shadow 設計書不存在——這正是 D 期要補的。

**D 期絕對不能做的**（違反任一即整 phase 重做）：

1. 不改 `AutopilotView` 一鍵主路徑的執行語意。唯一允許的改動 = 加一個 **flag 預設關閉** 的影子驗證入口（按鈕，使用者點擊才跑），flag 關閉時一鍵頁 DOM 與行為零變化。
2. 不做可編輯 node canvas（畫布維持 C4 唯讀契約）。
3. 不新增任何讓 guarded side effect（`renames_files`/`writes_profile`/`writes_csv`）從 UI 被觸發的入口；shadow run 永遠是 safe mode（allow/confirm 空）。
4. parity UI 不做泛用「執行比對」按鈕；比對的執行入口只有 (a) CLI `parity`、(b) 綁定剛完成一鍵 job 的受控 shadow 路徑（dedup、flag 門檻、後端驗證）。
5. shadow run 不寫使用者工作資料夾、不 rename、不影響一鍵已產出的結果。
6. 不在 useEffect/onChange/輪詢 callback 觸發 shadow / workflow_run / OCR（輪詢只准唯讀 status）。
7. 不動 normalize 比對規則的語意（改了會讓既有 parity 歷史不可比；要改是 E 期帶版本號的事）。

## 2. D 期範圍邊界

| 在範圍內 | 明確留給 E 期 |
|---|---|
| Shadow run 機器：一鍵完成後可手動觸發背景 workflow 影子跑 + 自動 parity 記錄 | **自動 shadow**（非點擊觸發）——會侵蝕「執行必須來自點擊」鐵則，等手動累積證據太慢再評估 |
| 換軌 gate 評估器（CLI + 唯讀 action + UI 呈現「還缺什麼」） | **真換軌**：一鍵消費 workflow 結果、AutopilotView 改執行路徑 |
| parity report schema v2（trigger / sample_kind / timing，append-only） | normalize 規則改版（需 schema version 與歷史遷移） |
| `test_smoke.py` 兩個舊字串 failure 修復（讓「full pytest 綠」重新有意義） | 可編輯畫布、allow/confirm 多重確認 UX、in-app parity 執行按鈕 |
| worker job.json O(n²) 進度寫入節流（C 期遺留） | worker 與 workflow engine 的執行統一 |
| vite chunk >500kB warning 收斂（@xyflow/react 拆 vendor chunk） | params overlay 編輯 node params、publish/revert profile nodes |

## 3. 現有 C 期成果解讀（D 期施工依據）

- **Parity 基礎**（`launcher/plugins/iso_tools/workflow/parity.py`）：`ParityReport.to_payload()`、`run_parity()`（legacy 側 in-process `_run_legacy_batch` L146、workflow 側 in-process + 投影）、`write_parity_report()`（含 `inputs_digest`）、`list_parity_reports(limit)`、報告落 `runtime_root()/.runtime/runs/parity/<ts>/report.json`。CLI `parity`（exit 6=violation）與 `parity-history`、唯讀 action `workflow_parity_history`（limit=10）都在。**缺**：報告沒有 `sample_kind`/`trigger`/`timing` 欄位——C5 那筆 real sample（equal、acceptable_diff_count=25、`inputs_digest: sha256:0796c5ef…`）在 gate 眼中是 `unknown`，**不能算 real 證據**；D 期起重新累積（幾分鐘的事，文件要明講，避免使用者以為證據遺失）。
- **一鍵 job 狀態**：`IsoBoard.tsx` L131 `batchJob`（`IsoJobPayload`）+ `oneClickStage`（idle/running/applying/review/done）；`AutopilotView` 是 props 驅動的展示層。shadow 按鈕掛 AutopilotView、handler 與狀態放 IsoBoard，與既有架構一致。
- **Flag 機制**：`.runtime/flags/` 檔案存在即啟用的慣例已有先例（`hide-to-tray-notified`）。shadow flag 沿用此慣例，不發明新機制。
- **Workflow job runner**（`launcher/app/tauri_workflow_job.py`）：`run_job()` 在 `run_workflow()` 完成後組 terminal job.json——shadow 的「比對 + 寫報告」後置步驟就插在這裡，跑在背景子程序內，前端只輪詢。
- **安全契約測試**（`tests/test_frontend_safety_contract.py` 5 條）：D3 在此 append shadow 規則，讓新入口被同一套靜態守門管住。
- **已知殘留**：`tests/test_smoke.py` 的 `test_iso_one_click_failure_card_is_handoff_only`（L135）與 `test_iso_autopilot_keeps_legacy_bridge_outside_one_click`（L151）仍讀 `App.tsx` 找已被 B 期抽到 `AutopilotView.tsx`/`IsoBoard.tsx` 的字串 → 2 failed（439 passed）。npm build chunk warning（gzip ≈154.92 kB）。C plan §11.1 表格中 C5 commit 寫 `pending`，實際是 `02a6747`（D0 順手在 postscript 補一行勘誤）。

## 4. 建議資料結構 / 新增檔案

### 4.1 parity report schema v2（append-only，舊報告仍可讀）

```json
{
  "schema_version": 2,
  "equal": true, "violations": [], "acceptable_diffs": ["…25 筆…"],
  "legacy_digest": "sha256:…", "workflow_digest": "sha256:…",
  "inputs_digest": "sha256:…",
  "trigger": "shadow",            // "cli" | "shadow"（v1 舊檔缺欄位 → 視為 "cli"）
  "sample_kind": "real",          // "real" | "fixture" | "unknown"（v1 → "unknown"）
  "iso_job_id": "…",              // shadow 才有；連回 .runtime/jobs/iso/<id>
  "workflow_run_id": "wf-…",
  "timing": { "legacy_ms": 71234, "workflow_ms": 68891 },   // legacy 取 job.json created_at→updated_at
  "created_at": "…"
}
```

### 4.2 shadow 銜接物

- `.runtime/jobs/iso/<job_id>/shadow.json`：shadow 觸發時寫 `{workflow_job_id, created_at}`。**這就是 dedup**：再次觸發直接回傳既有 workflow job payload（冪等重入，前端可恢復輪詢，不是錯誤）。
- workflow job 的 `request.json` 增 `shadow` 區塊：`{"iso_job_id": "...", "sample_kind": "real"}`；runner 看到此區塊才執行後置比對。
- `.runtime/flags/iso-shadow-run-enabled`：存在=啟用。

### 4.3 新增/修改檔案總表

| 檔案 | Phase | 動作 |
|---|---|---|
| `tests/test_smoke.py` | D0 | 修兩個測試的目標檔（App.tsx → AutopilotView.tsx / IsoBoard.tsx），保留原意圖 |
| `launcher/plugins/iso_tools/workflow/parity.py` | D1 | report v2 欄位、`write_parity_report` 增參數、`list_parity_reports` 透傳新欄位 |
| `launcher/app/tauri_iso_workflow.py` | D1/D2 | append actions：`workflow_shadow_run`、`workflow_set_shadow_flag`、`workflow_switchover_gate`；flag helpers |
| `launcher/app/tauri_workflow_job.py` | D1 | shadow 後置步驟（比對 + 寫報告 + job.json `parity_summary`） |
| `launcher/plugins/iso_tools/workflow/cli.py` | D1/D2 | `parity --sample-kind`；新子命令 `gate` |
| `launcher/plugins/iso_tools/workflow/gate.py`（新） | D2 | `evaluate_switchover_gate()` 純函式 + 條件定義 |
| `tests/test_iso_workflow_shadow.py`（新） | D1 | shadow 全行為測試 |
| `tests/test_iso_workflow_gate.py`（新） | D2 | gate 合成歷史測試 |
| `frontend/tauri-spike/src/isoWorkflow.ts` | D3 | types + helpers：`runIsoShadowVerify` / `loadIsoSwitchoverGate` / `setIsoShadowFlag` |
| `frontend/tauri-spike/src/iso/IsoBoard.tsx` / `AutopilotView.tsx` | D3 | shadowJob state + flag 門檻按鈕 + 一行結果 |
| `frontend/tauri-spike/src/iso/WorkflowInspector.tsx` | D3 | 「換軌守門」升級：gate 檢核表 + flag 開關 + 報告 chips |
| `tests/test_frontend_safety_contract.py` | D3 | append shadow 靜態規則 |
| `frontend/tauri-spike/vite.config.ts` | D3 | `manualChunks` 拆 `@xyflow/react` vendor chunk |
| `launcher/app/tauri_iso_worker.py` | D4 | 進度寫入節流（rows 全量寫 ≤ 每 5 頁或 1.5s 一次；counters 每頁；terminal 全量） |
| `tests/test_batch_detect_thread.py` 或新檔 | D4 | 寫入次數計數 + cancel 反應 + 120 頁哨兵 |


---

## 5. Phase 拆分（D0-D5）

> 通則：每 phase 一個 commit + push；結束先跑該 phase 測試命令全綠 + `git diff --stat` 對照檔案清單無越界。D1/D2 backend 🟢 checkpoint；D4 與 D1-D3 絕不混做（worker 節流是獨立風險面）。

### D0 — Pre-flight + 殘留收斂（docs + tests）

- **目標**：施工書入庫；修掉 `test_smoke.py` 兩個舊字串 failure，讓「full pytest 全綠」重新成為有效訊號（這是 gate 條件 3 的前提）。
- **修改檔案範圍**：本文件入庫；`tests/test_smoke.py`（僅兩個測試函式）；`docs/iso_pdf_workflow_c_phase_plan_2026-06-10.md` §11.1 的 C5 commit `pending` → `02a6747`（一行勘誤，append 風格註記）。
- **實作細節**：兩個測試的意圖（「一鍵失敗卡只做交接不自救」「legacy bridge 不在一鍵流程內」）**不變**，只把讀取目標從 `App.tsx` 改為實際持有該字串的 `frontend/tauri-spike/src/iso/AutopilotView.tsx` / `IsoBoard.tsx`（先 grep 確認字串現居地，再改斷言路徑；若字串真的已被刪除而非搬家 → 停下回報，不要憑空改斷言內容）。
- **禁止事項**：不動其他 smoke 測試；不為過測試而改前端字串。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_smoke.py -q
  & .venv\Scripts\python.exe -m pytest tests -q   # 期望 441 passed, 0 failed
  ```
- **驗收標準**：full pytest 0 failed；勘誤行存在。
- **Rollback 風險**：零（測試與文件）。
- **Commit**：`test(smoke): follow iso view extraction in smoke checks (D0)`（文件另一 commit：`docs(iso-workflow): add d phase plan (D0)`）

### D1 — Shadow run backend（核心機器）🟢

- **目標**：一筆已完成的一鍵 batch job，可被觸發一次（且僅一次）背景 workflow 影子跑，自動產出 parity report v2，全程不碰使用者資料夾、不影響 legacy 結果。
- **修改檔案範圍**：見 §4.3 D1 列。
- **實作細節（依序）**：
  1. `parity.py`：`write_parity_report(report, *, inputs, trigger="cli", sample_kind="unknown", iso_job_id=None, workflow_run_id=None, timing=None)`；payload `schema_version: 2`；`list_parity_reports` 透傳 `trigger`/`sample_kind`/`timing`（v1 檔缺欄位給預設 `"cli"`/`"unknown"`）。CLI `parity` 增 `--sample-kind {real,fixture}`，預設 `fixture`（**故意保守**：忘了標就不算 real，gate 不會被 fixture 灌水）。
  2. flag helpers（`tauri_iso_workflow.py`）：`_shadow_flag_path() = runtime_root()/".runtime"/"flags"/"iso-shadow-run-enabled"`；`workflow_set_shadow_flag_action`：request 用既有 `workflow` dict 欄位帶 `{"enabled": true|false}` → 建立/刪除 flag 檔，回 `{enabled}`。寫入僅限該固定路徑（無使用者輸入成分）。
  3. `workflow_shadow_run_action`：request `{action:"workflow_shadow_run", job_id:"<iso job id>"}`（重用既有 `job_id` 欄位，語意同 `job_status`）。驗證順序：flag 存在（否則 raise「影子驗證未啟用。請在節點式分頁開啟。」）→ `_job_dir_required` 取 job dir（既有消毒）→ `job.json` state 必須 `completed`（failed/cancelled/running 都 raise，訊息講明）→ `shadow.json` 已存在 → **冪等回傳**既有 workflow job payload（讀其 job dir）→ 否則：從 job dir `request.json` 取 11 個輸入欄位組 `workflow_inputs`，寫 workflow job（`_workflow_request_payload` 增 `shadow` 區塊 `{"iso_job_id", "sample_kind": "real"}`），spawn runner，寫 `shadow.json`，回 job payload。**shadow 一律 safe mode**：allow/confirm 強制空（hardcode，不讀 request）。
  4. `tauri_workflow_job.run_job`：result 組完、寫 terminal job.json **之前**，若 request 有 `shadow` 區塊且 run status ∈ {completed, completed_with_blocked}：讀 iso job dir 的 `job.json`（legacy result + created_at/updated_at 算 `legacy_ms`）→ `projection.plan_from_run` 投影自身 run → `compare_plans` → `write_parity_report(trigger="shadow", sample_kind=request 內值, iso_job_id, workflow_run_id, timing)` → job.json 增 `parity_summary: {equal, violation_count, acceptable_diff_count, report_path}`。run 失敗 → **不寫 history report**，job.json `parity_summary: {"status": "shadow_failed", "error": …}`（歷史只收真比對）。比對自身丟例外 → 同樣 shadow_failed，不讓比對失敗污染 job 終態（job 仍 completed，parity_summary 記 failure）。
  5. `tests/test_iso_workflow_shadow.py`（unittest.TestCase；PROJECT_ROOT_ENV 改道 tmp；monkeypatch `_spawn_iso_worker` 與 `_spawn_workflow_job` 同步執行）：
     - happy path：fixture 一鍵 job 跑完 → shadow → workflow job terminal 含 `parity_summary.equal=true`；report v2 欄位齊（trigger=shadow、sample_kind=real、timing 兩值 >0、iso_job_id 正確）。
     - 冪等：第二次 shadow 同 job_id → 回同 workflow_job_id，job root 下 workflow job 目錄數不變。
     - flag off → raise 中文訊息；job state=running/failed → raise。
     - 防污染：shadow 後 work folder `glob("**/*")` 與 shadow 前快照一致（沿用 pollution 測試 helper）；legacy `job.json` 位元組級不變（shadow.json 是新檔，job.json 不动）。
     - workflow 失敗（壞輸入注入）→ 無新 parity report、parity_summary.status=shadow_failed。
     - `job_id="../escape"` → `_job_dir` 既有消毒擋下。
- **禁止事項**：不動 `run_workflow`/executor；不動 legacy worker；不在 action 層跑比對（必須在 runner 子程序，避免 Tauri 呼叫阻塞）；shadow 不接受自訂 workflow path（鎖死 safe POC）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_shadow.py tests\test_iso_workflow_parity.py tests\test_iso_workflow_parity_history.py tests\test_iso_workflow_job.py tests\test_tauri_iso_workflow.py tests\test_iso_workflow_pollution.py -q
  ```
- **驗收標準**：上列全綠；手跑 CLI `parity --sample-kind real` 產出 v2 report 且 `parity-history` 顯示新欄位。
- **Rollback 風險**：append-only（兩個新 action + runner 後置步驟 + report 欄位）；revert 單 commit 回 C 期狀態，v2 report 殘檔對 v1 讀取器無害（欄位多不破壞）。
- **Commit**：`feat(iso-workflow): add shadow run with parity recording (D1)`
- **🟢 Checkpoint**：可停下交接。

### D2 — 換軌 gate 評估器（backend）🟢

- **目標**：gate 從「文件裡的四句話」變成可執行的判定：CLI 一條命令、Tauri 一個唯讀 action，輸出每條條件的 met/unmet 與差多少。
- **修改檔案範圍**：新增 `gate.py`、`tests/test_iso_workflow_gate.py`；`cli.py` 增 `gate` 子命令；`tauri_iso_workflow.py` append `workflow_switchover_gate` action。
- **實作細節**：
  ```python
  # gate.py
  GATE_WINDOW = 5
  GATE_MIN_REAL = 2
  def evaluate_switchover_gate(*, reports: list[dict] | None = None) -> dict:
      # reports 預設 list_parity_reports(limit=GATE_WINDOW)["reports"]
      # G1 recent_all_equal：恰取最近 5 筆且全 equal（不足 5 筆 → unmet，detail="目前 N/5 筆"）
      # G2 real_samples：該 5 筆中 sample_kind=="real" 數 ≥ 2（"unknown"/"fixture" 不計）
      # G3 pollution_suite：met=None（manual），detail 給確切命令
      #     "python -m pytest tests/test_iso_workflow_pollution.py tests/test_frontend_safety_contract.py -q"
      # G4 shadow_design：檢查 Path("docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md").exists()（cwd=repo root）；找不到 → met=None
      # ready = (G1 and G2 and G4) and G3 is not False   ——文案輸出「可進入 E 期評估」/「尚未可換軌（n/4）」
      # 回傳 {schema_version:1, ready, headline, conditions:[{id,title,met,detail}], window:[每筆摘要], evaluated_at}
  ```
  action `workflow_switchover_gate` 額外回 `shadow_flag_enabled`（讀 flag 檔）。CLI `gate [--json]` exit 0=ready、7=not ready（新 exit code，僅供腳本判讀，not ready 不是錯誤）。
- **測試（合成 reports 注入，不碰真 runtime）**：5 equal+2 real → ready；4 筆 → not（detail 含 4/5）；5 equal+1 real → not；5 筆中 1 violation → not；v1 舊報告（無 sample_kind）佔窗 → 計為 unknown 不算 real；fixture 5 筆全 equal → not（G2 擋住灌水）。
- **禁止事項**：gate 不觸發任何執行（純讀檔）；不把 G3 做成自動跑 pytest（評估器保持毫秒級）。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_gate.py tests\test_tauri_iso_workflow.py -q
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli gate --json
  ```
- **驗收標準**：合成測試全綠；真環境 `gate --json` 輸出 not ready 且 detail 正確指出缺口（此刻應為 1/5 筆、0 real）。
- **Rollback 風險**：純新增；revert 無影響。
- **Commit**：`feat(iso-workflow): add switchover gate evaluator (D2)`
- **🟢 Checkpoint**：可停下交接。


### D3 — 最小 UX：影子驗證入口 + gate 呈現（frontend）

- **目標**：使用者看得懂兩件事——「這次一鍵的影子驗證結果」與「現在能不能換軌、缺什麼」。不做任何漂亮 editor。
- **修改檔案範圍**：見 §4.3 D3 列（isoWorkflow.ts / IsoBoard.tsx / AutopilotView.tsx / WorkflowInspector.tsx / test_frontend_safety_contract.py / vite.config.ts）。
- **實作細節**：
  1. `isoWorkflow.ts` append：
     ```ts
     export interface IsoSwitchoverGateCondition { id: string; title: string; met: boolean | null; detail: string; }
     export interface IsoSwitchoverGateVerdict { schema_version: number; ready: boolean; headline: string;
       conditions: IsoSwitchoverGateCondition[]; window: IsoParityReportSummary[]; evaluated_at: string;
       shadow_flag_enabled?: boolean; }
     // IsoParityReportSummary append: trigger?: string; sample_kind?: string; timing?: {legacy_ms?: number; workflow_ms?: number};
     export async function runIsoShadowVerify(jobId: string): Promise<IsoNodeWorkflowJobPayload>;   // action: workflow_shadow_run
     export async function loadIsoSwitchoverGate(): Promise<IsoSwitchoverGateVerdict>;              // action: workflow_switchover_gate
     export async function setIsoShadowFlag(enabled: boolean): Promise<{ enabled: boolean }>;       // action: workflow_set_shadow_flag
     ```
  2. `IsoBoard.tsx`：`shadowJob` state（沿用 C3 模式放 board 層，切 view 不丟）+ `handleShadowVerify`（**onClick 專用**；`isWorkflowJobRunning(shadowJob)` 防重入）+ 輪詢沿用既有 workflow job 輪詢模式（唯讀 status）。flag 狀態由 `loadIsoSwitchoverGate()` 在使用者**開啟節點式分頁或按重新整理時**載入（不做全域自動輪詢）。
  3. `AutopilotView.tsx`：僅當 `shadowFlagEnabled && (oneClickStage === "done" || oneClickStage === "review") && batchJob?.state === "completed"` 顯示一列：「影子驗證（實驗）」按鈕 + 結果一行（`parity_summary.equal` → 「✓ 影子一致」/ violation → 「✗ 發現差異 N 筆（節點式分頁看細節）」/ shadow_failed → 「影子執行失敗（不影響一鍵結果）」）。flag 關閉 → 此列完全不渲染（一鍵頁 DOM 不變）。按鈕點過（shadow.json 冪等）→ 顯示結果列、按鈕 disabled「已驗證」。
  4. `WorkflowInspector.tsx` 換軌守門區升級：gate headline 大字 +四條件 checklist（met=true ✓ 綠 / false ✗ 紅含 detail / null ⚠ 灰「手動確認」附命令）+ flag 開關（呼叫 `setIsoShadowFlag`，旁註「開啟後一鍵完成會出現影子驗證按鈕；影子只讀不寫、不改名」）+ 最近 reports 列表加 `trigger`/`sample_kind` chips（real=藍、fixture=灰、unknown=灰斜體）與 timing 兩欄。
  5. `vite.config.ts`：`build.rollupOptions.output.manualChunks = { "vendor-xyflow": ["@xyflow/react"] }` 收斂 >500kB warning；build 體積記進 commit message。
  6. `test_frontend_safety_contract.py` append 三條：`runIsoShadowVerify(` 呼叫點恰 1 處且不在 useEffect 區塊；`workflow_shadow_run` 字串只出現在 isoWorkflow.ts；`setIsoShadowFlag` 呼叫點恰 1 處（Inspector 開關）。
- **禁止事項**：不加任何自動觸發（含「一鍵完成自動跑影子」——那是 E 期評估的事）；不在工作台/調校加 shadow 入口；不改 AutopilotView 其他區塊；gate 載入不得放進固定 interval。
- **測試命令**：
  ```powershell
  cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit
  & .venv\Scripts\python.exe -m pytest tests\test_frontend_safety_contract.py -q
  ```
- **驗收標準**：tsc/build/vitest/守門綠；flag off 時一鍵頁 git diff 渲染等價（手動煙測一次：開 flag → 跑一鍵（樣本）→ 按影子驗證 → 節點式分頁看到 gate 與 report chips）；chunk warning 消失或 vendor chunk 分離可見。
- **Rollback 風險**：UI 增量 + vite 設定一行；revert 後 backend 能力仍在（CLI 可用）。
- **Commit**：`feat(iso-workflow): shadow verify entry and switchover gate panel (D3)`

### D4 — worker 進度寫入節流（backend perf，C 期遺留）

- **目標**：消除 `tauri_iso_worker._write_progress` 每頁全量重寫 job.json（含累積 rows）的 O(n²) 行為，大 PDF 不再越跑越慢；cancel 反應速度與終態 schema 完全不變。
- **修改檔案範圍**：`launcher/app/tauri_iso_worker.py`（`_write_progress` 與呼叫點）；測試（`tests/test_batch_detect_thread.py` append 或新 `tests/test_iso_worker_progress.py`）。
- **實作細節**：節流規則——`progress` 計數器每頁更新；`rows`/`issues` 全量寫入僅在（a）距上次全量寫 ≥1.5s **或** 每 5 頁、（b）cancel 偵測當下、（c）終態，三者觸發。cancel 檢查仍每頁一次（迴圈頂端，不動）。job.json schema 與終態內容位元組級語意不變（中途輪詢可能晚 ≤5 頁看到 rows——前端僅消費 `progress` 與 events 做進度條，rows 全量消費在 terminal；D3 前已驗證 `AutopilotView` 以 `batchJob.progress`/`events` 為主，若 grep 發現有依賴中途 rows 的消費點 → 停下回報）。
- **禁止事項**：不改 rows 內容與順序；不動 run log 寫入；不動 cancel 語意；不引入背景 thread。
- **測試命令**：
  ```powershell
  & .venv\Scripts\python.exe -m pytest tests\test_batch_detect_thread.py tests\test_iso_worker_progress.py tests\test_tauri_iso_workflow.py tests\test_iso_workflow_shadow.py -q
  ```
- **驗收標準**：監測寫入次數的測試證明 120 頁 fixture 全量寫 ≤ 26 次（120/5+終態+餘量）而非 120 次；cancel 在第 N 頁觸發 → ≤1 頁內生效；終態 rows=120 完整；既有 batch 測試零修改通過（若需改既有測試斷言 → 那是行為破壞，停下）。
- **Rollback 風險**：單檔單函式；revert 即回每頁全寫。最大風險是隱藏的「中途 rows 消費者」——驗收已含 grep 防線。
- **Commit**：`perf(iso): throttle worker progress writes for large pdfs (D4)`

### D5 — 收尾：真樣本證據 + 合流（operator + docs）

- **目標**：用真機器跑出 D 期第一批 v2 證據；記錄 gate 現狀；合流打 tag。
- **操作步驟（operator 在 Windows 跑，輸出原文進 postscript）**：
  ```powershell
  # 1) 開 flag（或在節點式分頁 UI 開）
  # 2) 對樣本資料夾跑一次完整一鍵（C:\Users\a0976\Downloads\t）→ 完成後按「影子驗證」
  # 3) CLI 再補一筆 real：
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\poc_inputs.json --sample-kind real --json
  # 4) 看 gate：
  & .venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli gate --json
  ```
- **預期**：兩筆 real（1 shadow + 1 cli）、gate not ready（窗內筆數/real 數視累積而定）——**not ready 是正確輸出**，照實記錄。若任一筆 violation → 停工，report 原文進回報，不准修兩側程式讓它變綠。
- **修改檔案範圍**：本文件 append「D 期完工 Postscript」（commit 清單、實跑命令輸出、gate 快照、殘留）；merge `codex/iso-workflow-d` → `codex/tauri-react-spike`（--no-ff）+ tag `iso-workflow-d-v1` + push；刪本地工作分支。
- **測試命令**：§「測試矩陣」全列（見 Top10 後）。
- **驗收標準**：全矩陣綠；postscript 含 gate JSON 快照與兩筆 real 證據；tag 推上 origin。
- **Rollback 風險**：docs only。
- **Commit**：`docs(iso-workflow): record d phase completion and gate snapshot (D5)`


---

## 6. Top 10 爆點審查

| # | 爆點 | 嚴重度 | 為什麼會爆 | 最可能位置 | 如何重現 | Codex 最小修補 | 進 D 期？ |
|---|---|---|---|---|---|---|---|
| 1 | Shadow 造成 OCR/worker 過載 | 🔴 高 | 影子=完整重跑 batch detect，OCR 成本 ×2；若與下一次一鍵併發，同資料夾雙 worker 互踩 | `workflow_shadow_run_action`、`detection.py` worker 模式 | 一鍵剛完成立刻按影子、影子未完又跑新一鍵 | 順序化設計：影子只在 job `completed` 後可觸發 + `shadow.json` 冪等 + flag 預設關；不做自動觸發 | ✅ D1（設計即防線） |
| 2 | Shadow 寫使用者資料夾 | 🔴 高 | safe POC 含 split 節點；若 legacy 用 combine_pdf 且 `_pages` 被使用者刪掉，影子會重拆寫使用者資料夾 | `nodes/sources.py` split、shadow inputs 組裝 | 跑完一鍵→手刪 `_pages`→按影子 | 接受「重拆＝功能本體」但必須記錄：split 的 side_effect decision 已進 run log；測試固化「未刪 pages 時影子零新檔」；文件明示唯一例外 | ✅ D1（測試+文件） |
| 3 | ROI slider / useEffect 觸發影子或 OCR | 🔴 高 | 新增了 `runIsoShadowVerify` 這條新執行路徑，歷史災難都是新路徑接錯觸發源 | `IsoBoard.tsx` handler、`AutopilotView.tsx` | 把影子呼叫放進 useEffect/輪詢 | D3 靜態守門：恰 1 呼叫點、不在 useEffect；輪詢只准 `loadIsoWorkflowJobStatus` | ✅ D3 |
| 4 | Parity false negative（假等價） | 🔴 高 | normalize 吸太多：basename 比對撞名、P15 排除、issues 只比 code multiset——理論上可掩蓋真差異 | `parity.py` `_normalize_rows`/`_normalize_pilot` | 兩列同 basename 不同目錄 | D 期**不改 normalize**（歷史可比性優先）；靠既有變異哨兵 + report 保留 `acceptable_diffs` 全文供人工抽查；normalize 改版 = E 期帶 schema v3 | ⚠️ 記錄，E 期 |
| 5 | Parity false positive（環境差異判違規）→ gate 永遠 not ready | 🟠 中 | timing/路徑/候選清單已正規化，但新欄位（如 B11 `record_path`）若兩側不對稱會變 violation | `parity.py` `_record_removed_top_level` | legacy 側 apply 後帶 `record_path`，workflow 投影無此欄 | D1 happy-path 測試若見非預期 violation → 修「移除清單」把該欄列入 acceptable（這是白名單維護，不是語意變更） | ✅ D1（隨測試） |
| 6 | Gate 證據被 fixture 灌水或誤計 | 🟠 中 | 5 筆窗內若混入 fixture/unknown 全 equal 也不該 ready；CLI 忘標 sample-kind | `gate.py` G2、`cli.py` parity | 連跑 5 次 fixture parity 後查 gate | `--sample-kind` 預設 fixture（保守）；G2 只數 `real`；測試覆蓋灌水場景 | ✅ D2 |
| 7 | Flag 殘留誤開 / 舊報告 unknown 困惑 | 🟡 低 | flag 檔忘了關→影子按鈕常駐；C5 那筆 real 在 v2 眼中是 unknown，使用者以為證據掉了 | flag 檔、gate 視窗 | 開 flag 後幾天回來看 | gate 回傳 `shadow_flag_enabled` + Inspector 顯示開關現況；文件/UI 明示「v1 報告不計入 real，需重累積」 | ✅ D2/D3 |
| 8 | run log / job dir 路徑逃逸回歸 | 🟠 中 | 新 action `workflow_shadow_run` 接 `job_id`，等於新增一個路徑入口 | `_job_dir`（既有 regex 消毒）、`workflow_shadow_run_action` | `job_id="../../runs"` | 沿用 `_job_dir_required`（已消毒）+ D1 測試含逃逸字串；C1 的 run-dir guard 回歸測試照跑 | ✅ D1 |
| 9 | 大 PDF：job.json O(n²) 寫入 + 影子讓成本翻倍 | 🟠 中 | `_write_progress` 每頁全量重寫含累積 rows；300 頁時 IO 失控；影子再 ×2 | `tauri_iso_worker.py` L90 附近 | 300 頁 PDF 跑一鍵+影子 | D4 節流（每 5 頁/1.5s）；120 頁哨兵測試上限寫入次數 | ✅ D4 |
| 10 | CSV 污染 / Excel lock / guarded UI 入口回歸 | 🔴 高（恆常） | 每加一條新路徑（shadow、gate、flag）都是回歸面；Excel 鎖檔在 retention 修剪時也會遇到（刪不掉開著的舊檔） | C1/C2 既有防線、`_prune_exports` | 開著舊 CSV 再匯出 51 份 | 不新增程式：每 phase 跑 pollution + safety contract 全套；D1 防污染測試含 shadow 場景；修剪遇鎖檔靜默跳過（C2 已做，回歸列管） | ✅ 每 phase 回歸 |

## 7. 最終換軌 gate（E 期開工條件，D2 起可機器查核）

```text
G1 最近 5 筆 parity report 全部 equal（violation_count=0）
G2 該 5 筆中 sample_kind=="real" ≥ 2（shadow 觸發自動標 real；CLI 需 --sample-kind real）
G3 防污染 + 前端安全契約測試套件最近一次執行全綠（手動 attest，命令見 gate 輸出）
G4 shadow run 設計書存在（= 本文件；D0 入庫即達成）
查核：python -m launcher.plugins.iso_tools.workflow.cli gate --json   （exit 0=ready / 7=not ready）
```

達成後 E 期才可討論：一鍵消費 workflow 結果（feature flag 雙軌觀察期 → 替換）、自動 shadow、normalize v3、可編輯畫布。**gate ready ≠ 自動換軌**，E 期仍需自己的施工書。

## 8. 測試矩陣（D5 全跑；各 phase 跑對應列）

| 範圍 | 命令 | D0 | D1 | D2 | D3 | D4 | D5 |
|---|---|---|---|---|---|---|---|
| Full pytest | `python -m pytest tests -q`（期望 0 failed） | ✅ | — | — | — | — | ✅ |
| Shadow | `pytest tests\test_iso_workflow_shadow.py -q` | — | ✅ | — | — | ✅ | ✅ |
| Gate | `pytest tests\test_iso_workflow_gate.py -q` | — | — | ✅ | — | — | ✅ |
| Parity 全套 | `pytest tests\test_iso_workflow_parity.py tests\test_iso_workflow_parity_history.py -q` | — | ✅ | ✅ | — | — | ✅ |
| 防污染 + 安全契約 | `pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q` | — | ✅ | — | ✅ | ✅ | ✅ |
| Backend actions | `pytest tests\test_tauri_iso_workflow.py tests\test_iso_workflow_job.py -q` | — | ✅ | ✅ | — | ✅ | ✅ |
| Worker 進度 | `pytest tests\test_batch_detect_thread.py tests\test_iso_worker_progress.py -q` | — | — | — | — | ✅ | ✅ |
| 前端 | `cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit` | — | — | — | ✅ | — | ✅ |
| Real sample（operator） | D5 步驟 1-4（影子一筆 + CLI 一筆 + gate 快照） | — | — | — | — | — | ✅ |
| 人工煙測 | D3 一次（flag→一鍵→影子→gate 面板） | — | — | — | 1 | — | — |

無 pytest 環境：同名模組 `python -m unittest tests.<module> -v`。

## 9. Git / Rollout

- 分支：`git switch -c codex/iso-workflow-d`（自 `codex/tauri-react-spike` @ `4780832`）。一次只活這一條。
- Commit 順序：`docs(D0)` → `test(smoke D0)` → `feat(D1)` → `feat(D2)` → `feat(D3)` → `perf(D4)` → `docs(D5)`。
- Rollback：每 phase 單 commit 可獨立 revert；D1 revert 後殘留的 v2 report/`shadow.json` 為惰性資料，無需清理；D3 revert 不影響 CLI 能力；D4 revert 回每頁全寫（慢但正確）。
- Merge/tag 條件：D5 矩陣全綠 + real sample 步驟有輸出原文 → `git merge --no-ff codex/iso-workflow-d -m "merge(iso-workflow): complete D phase"` → `git tag -a iso-workflow-d-v1 -m "shadow run + switchover gate"` → push 兩者 → 刪本地分支。
- 環境註記（沿用 C 期）：沙箱掛載視圖可能尾端截斷、git 報 `improper chunk offset`（commit-graph 視圖假象）；Windows 以 `git fsck --connectivity-only` 為準；`.qwen/` 永不 stage；不用 `git add -A`。

## 10. 給 Codex 的照抄開工指令

```text
請讀 docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md（本文件），它是 D 期唯一 active 施工書。

Pre-flight（不寫碼）：
1. cd C:\Users\a0976\Documents\GitHub\桌面輔助系統
2. git fsck --connectivity-only
3. git status --short --branch；git log --oneline -3   # 期望 tip=4780832、工作樹乾淨（.qwen/ 除外，永不 stage）
4. git switch codex/tauri-react-spike && git pull --ff-only
5. git switch -c codex/iso-workflow-d
6. git add docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md && git commit -m "docs(iso-workflow): add d phase plan (D0)" && git push -u origin codex/iso-workflow-d

然後照 D0→D1→D2→D3→D4→D5 施工：
- 每 phase 一個 commit + push，用給定 commit message；結束先跑該 phase 測試命令全綠 + git diff --stat 不越界。
- D1、D2 是可停下交接的 checkpoint；D4 絕不與 D1-D3 混做。
- 鐵則：shadow 一律 safe mode（allow/confirm 硬編碼為空）；影子只能由使用者點擊觸發；flag 檔 .runtime/flags/iso-shadow-run-enabled 預設不存在；一鍵主路徑零行為變更（flag 關閉時 DOM 不變）；不做自動 shadow；不改 parity normalize 語意；節點式維持唯讀畫布。
- D0 修 test_smoke 兩個測試時：先 grep 確認舊字串現居 AutopilotView.tsx/IsoBoard.tsx，字串若已不存在就停下回報，不准改斷言內容硬過。
- D1 happy-path 若出現非預期 violation（如 record_path 欄位不對稱）：把該欄位加入 normalize 移除白名單（這是維護，不是語意變更），並記進 commit message。
- D5 real sample 任一筆 violation：停工，report 原文進回報，不准修任一側讓它變綠。
- 遇到邊界不明：停下寫短報告（現況/選項/建議）。絕不做 E 期內容：不改一鍵執行語意、不做自動 shadow、不做可編輯畫布、不動 normalize 規則版本。
- D5 完成後：merge --no-ff 回 codex/tauri-react-spike、tag iso-workflow-d-v1、push、停工回報（commit 清單、矩陣輸出、gate JSON 快照、build 體積、殘留與風險）。
```

## 11. 2026-06-10 收工暫停點 / 2026-06-11 待辦

### 已完成並推上 GitHub

- 目前分支：`codex/iso-workflow-d`。
- 目前 tip：`b98a3b4 perf(iso): throttle worker progress writes for large pdfs (D4)`，已 push 到 `origin/codex/iso-workflow-d`。
- 工作樹：只有 `.qwen/` 未追蹤；依本文件規則永不 stage。
- D0-D4 已完成：D0 文件與 smoke 修正、D1 shadow parity v2、D2 gate evaluator、D3 影子驗證入口與 gate panel、D4 worker progress 全量寫入節流。

### 今日已跑過的 D5 驗證

```text
python -m pytest tests -q
461 passed in 58.51s

python -m pytest tests\test_iso_workflow_shadow.py -q
3 passed in 0.89s

python -m pytest tests\test_iso_workflow_gate.py -q
7 passed in 0.22s

python -m pytest tests\test_iso_workflow_parity.py tests\test_iso_workflow_parity_history.py -q
8 passed in 1.79s

python -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q
13 passed in 2.99s

python -m pytest tests\test_tauri_iso_workflow.py tests\test_iso_workflow_job.py -q
32 passed in 2.83s

python -m pytest tests\test_batch_detect_thread.py tests\test_iso_worker_progress.py -q
6 passed in 1.10s

cd frontend\tauri-spike
npx tsc --noEmit
npm run test:unit
1 file / 3 tests passed
npm run build
main bundle gzip 53.61 kB; vendor-xyflow gzip 101.64 kB; no large chunk warning
```

### 今日已跑過的 real shadow sample

資料夾：`C:\Users\a0976\Downloads\t`

使用輸入：
- `page_folder`: `C:\Users\a0976\Downloads\t\testing_pages`
- `iso_list`: `C:\Users\a0976\Downloads\t\HP6精濾區配管工事-ISO圖號清單-115.04.23.xlsx`
- `sheet_name`: `DWG NO.ALL`
- `serial_col`: `11`
- `line_col`: `2`
- `detect_serials`: `False`

結果：

```json
{
  "iso_job_id": "d5-real-iso-job",
  "iso_state": "completed",
  "iso_rows": 4,
  "workflow_job_id": "shadow-c8089b369a85",
  "workflow_state": "completed",
  "parity_summary": {
    "status": "recorded",
    "equal": true,
    "violation_count": 0,
    "acceptable_diff_count": 25,
    "report_path": "C:\\Users\\a0976\\Documents\\GitHub\\桌面輔助系統\\.runtime\\runs\\parity\\20260610_175401_ade94f\\report.json"
  }
}
```

### 明日 2026-06-11 待辦

1. 先確認狀態：

   ```powershell
   git switch codex/iso-workflow-d
   git status --short --branch
   git log --oneline -8
   ```

2. 補跑 D5 的 CLI real parity，使用同一份真樣本，需標 `--sample-kind real`：

   ```powershell
   python -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json <inputs-json> --sample-kind real --json
   ```

   可重用今日的 `C:\Users\a0976\Downloads\t` 輸入。若沒有現成 inputs json，就先生成一份臨時檔放 `.runtime\temp\d5_real_inputs.json`。

3. 跑 gate 快照並照實記錄：

   ```powershell
   python -m launcher.plugins.iso_tools.workflow.cli gate --json
   ```

   預期多半仍是 `ready=false`；not ready 是正確結果，只要 detail 能指出缺口即可。

4. 把 D5 完工 Postscript 補在本文件：commit 清單、完整矩陣輸出、real shadow report、CLI real parity report、gate JSON 快照、殘留風險。

5. Commit + push D5 文件：

   ```powershell
   git add docs/iso_pdf_workflow_d_phase_plan_2026-06-10.md
   git commit -m "docs(iso-workflow): record d phase completion and gate snapshot (D5)"
   git push origin codex/iso-workflow-d
   ```

6. 若 D5 全部綠且沒有 violation，才合流：

   ```powershell
   git switch codex/tauri-react-spike
   git pull --ff-only
   git merge --no-ff codex/iso-workflow-d -m "merge(iso-workflow): complete D phase"
   git tag -a iso-workflow-d-v1 -m "shadow run + switchover gate"
   git push origin codex/tauri-react-spike
   git push origin iso-workflow-d-v1
   ```

7. 回報使用者：D 期已完成/或 gate 尚缺幾筆 real evidence；不要開 E 期內容，除非使用者明確同意。

## 12. D 期完工 Postscript（2026-06-11）

### 結論

D 期已完成「影子驗證 + switchover gate + worker progress 節流」的先導施工；沒有進入 E 期範圍。  
E 期換軌 gate 目前仍是 `ready=false`，原因是最近 parity window 只有 `4/5` 筆，這是正確的保守輸出；目前沒有 parity violation。

### Commit 清單

```text
bb3bd62 docs(iso-workflow): add d phase plan (D0)
43fe1b7 test(smoke): follow iso view extraction in smoke checks (D0)
8cad29c feat(iso-workflow): add shadow run with parity recording (D1)
2852783 feat(iso-workflow): add switchover gate evaluator (D2)
0497f19 feat(iso-workflow): shadow verify entry and switchover gate panel (D3)
b98a3b4 perf(iso): throttle worker progress writes for large pdfs (D4)
64c6238 docs(iso-workflow): record d5 pause point
```

### 2026-06-11 最終驗證

```text
python -m pytest tests -q
461 passed in 56.90s

cd frontend\tauri-spike
npx tsc --noEmit
npm run test:unit
Test Files 1 passed (1)
Tests 3 passed (3)

npm run build
main bundle gzip 53.61 kB
vendor-xyflow gzip 101.64 kB
no large chunk warning
```

昨日 D5 分組矩陣也已全綠（見本文件第 11 節）：Shadow、Gate、Parity、防污染 + 安全契約、Backend actions、Worker 進度全部通過。

### Real Shadow Sample

資料夾：`C:\Users\a0976\Downloads\t`

```json
{
  "iso_job_id": "d5-real-iso-job",
  "iso_state": "completed",
  "iso_rows": 4,
  "workflow_job_id": "shadow-c8089b369a85",
  "workflow_state": "completed",
  "parity_summary": {
    "status": "recorded",
    "equal": true,
    "violation_count": 0,
    "acceptable_diff_count": 25,
    "report_path": "C:\\Users\\a0976\\Documents\\GitHub\\桌面輔助系統\\.runtime\\runs\\parity\\20260610_175401_ade94f\\report.json"
  }
}
```

### CLI Real Parity Sample

輸入檔：`.runtime\temp\d5_real_inputs.json`  
命令：

```powershell
python -m launcher.plugins.iso_tools.workflow.cli parity --inputs-json .runtime\temp\d5_real_inputs.json --sample-kind real --json
```

結果：

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
  "report_path": "C:\\Users\\a0976\\Documents\\GitHub\\桌面輔助系統\\.runtime\\runs\\parity\\20260611_080126_a2fe3a\\report.json"
}
```

### Gate Snapshot

命令：

```powershell
python -m launcher.plugins.iso_tools.workflow.cli gate --json
```

Exit code：`7`（not ready，非錯誤）

```json
{
  "schema_version": 1,
  "action": "workflow_switchover_gate",
  "ready": false,
  "headline": "尚未可換軌（2/4）",
  "evaluated_at": "2026-06-11T08:01:45",
  "conditions": [
    {
      "id": "recent_all_equal",
      "title": "最近 5 筆 parity 全一致",
      "met": false,
      "detail": "目前 4/5 筆，equal 4/5 筆。"
    },
    {
      "id": "real_samples",
      "title": "最近 5 筆至少 2 筆 real sample",
      "met": true,
      "detail": "已達成"
    },
    {
      "id": "pollution_suite",
      "title": "防污染與前端安全契約綠燈",
      "met": null,
      "detail": "python -m pytest tests/test_iso_workflow_pollution.py tests/test_frontend_safety_contract.py -q"
    },
    {
      "id": "shadow_design",
      "title": "Shadow run 設計書已入庫",
      "met": true,
      "detail": "docs\\iso_pdf_workflow_d_phase_plan_2026-06-10.md"
    }
  ],
  "window_summary": [
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

### 殘留與下一步

- D 期可合流；gate `ready=false` 不代表 D 期失敗，只表示還不能進 E 期真換軌。
- E 期若要開工，至少要先補足最近 5 筆 parity window，並由 gate 顯示 `recent_all_equal=true`；`pollution_suite` 仍是手動 attest 條件。
- 不要在沒有新施工書的情況下做 E 期內容：不改一鍵執行語意、不做自動 shadow、不做可編輯節點畫布、不動 normalize 規則版本。
