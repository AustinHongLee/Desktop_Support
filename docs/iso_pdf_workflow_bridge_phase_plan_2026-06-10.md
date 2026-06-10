# ISO Node Workflow — Post-POC Bridge Phase 施工書

> Date: 2026-06-10
> 角色：最高層架構審查 + 下一階段施工規劃（一次性裁決版）
> 母文件：`docs/iso_pdf_node_workflow_codex_handoff_2026-06-10.md`（下稱「母文件」，其 §15 已同步記錄本裁決）
> 本文件是下一階段（Bridge Phase）唯一 active 施工入口。

## 0. 已驗證的現場事實（裁決依據，Codex 不必重查，但 B1 仍要照 checklist 驗一次）

- `codex/iso-node-workflow-poc` tip = `6f9dbdc`，完整鏈：`081ed04 → fe8b4ee → b0d277a → ff03fb2 → 82f848f → df80420 → e7ac248 → 1b5e0d9 → 858a7fe → 6f9dbdc`，且**已推上 origin**。
- `origin/codex/tauri-react-spike` 停在 `ff03fb2`（POC 六個 commit 尚未合回主線）。
- `6f9dbdc` 實際內容已逐行檢視：對 `IsoWorkflowRequest` **append-only** 加了 `workflow_path`、`workflow` 兩個 optional 欄位；`_dispatch_request` 尾端 append 三個純讀 action（`workflow_list_nodes` / `workflow_load` / `workflow_validate`）；workflow 模組全部 **lazy import**（函式內 import，不影響既有 21 個 action 的啟動路徑）；前端只加型別與三個 helper。既有 action 的 request/response 欄位零變動。技術品質合格。
- 母文件 §14 之前已存在 Codex 自行 append 的「建議順序」段，其第 1 步就是這三個 read-only action——**母文件內部本來就自相矛盾**（§13 禁止事項 vs 文末建議順序），6f9dbdc 是照後者做的。
- ⚠️ 環境陷阱（已親測）：Linux 沙箱掛載視圖下，多個最近改過的檔案呈現**尾端截斷**（`tauri_iso_workflow.py` 磁碟視圖 53218B vs git blob 56390B、`.git/HEAD` 截斷成 `codex/iso-node-workflow-`）。這是已知的 Windows↔Linux 掛載同步假象，**不是 repo 損壞**；Windows 端以 `git status` / `git symbolic-ref HEAD` 為準，異常時照 B1 修復步驟處理。沙箱端要讀真內容一律 `git show <ref>:<path>`。
- 架構審查時曾標記 `frontend/tauri-spike/src/App.tsx` 可能有一行純空白差異；Codex B1 實測 `git status` 未列出此檔，因此未執行 restore。

---

# A. 架構裁決：6f9dbdc 怎麼處理

## A.1 裁決：**保留，原地重定位為 Bridge Phase 的 B0 commit**

四個選項的評估：

| 選項 | 評估 | 結論 |
|---|---|---|
| 保留在目前分支 | 程式碼 append-only、已驗證（npm build ✓、workflow 40 tests ✓、回歸 28 tests ✓）、方向 = 母文件 §12 表格的前三列 | ✅ **主建議** |
| revert | 丟掉已驗證工作換取流程潔癖；revert commit 本身又是一個要管理的 commit；之後還是要原樣重做 | ❌ 純損失 |
| cherry-pick 到新分支 | 對單人開發者增加一條分支與一次 conflict 風險，換到的只是「歷史好看」 | ❌ 成本>收益 |
| soft reset 拆 phase | 6f9dbdc 本來就是單一原子 commit、範圍清晰（3 檔、218 行），拆了沒有更小的可驗證單元 | ❌ 無意義 |

裁決理由：這次違規是**文件邊界錯誤，不是程式碼錯誤**。Phase 7 的 bound（docs-only、不碰前端、不加 action）寫給「POC 期」；6f9dbdc 做的事是母文件 §12 早已規劃的「未來 Tauri actions」第一步，且做法完全符合 §12 的規格（append-only、read-only、不動既有 schema）。對個人開發者而言，正確動作是**把帳記對**（追認它是下一階段的第一個 commit），而不是把對的程式碼砍掉重練。流程債用文件還（見 §F / 母文件 §15），不用 git 還。

## A.2 保留之下，母文件怎麼修才不自相矛盾

三條修法（已寫進母文件 §15，B1 commit 入庫）：

1. **宣告 POC 完成點 = `858a7fe`**，並打 annotated tag `iso-workflow-poc-v1` 釘住（§13 的禁止事項自此「對 POC 期封存生效」，不再約束後續階段）。
2. **追認 6f9dbdc = Bridge Phase B0**：合規性以本文件（Bridge 施工書）的非目標清單為準，6f9dbdc 逐條對照通過。
3. **訂出新規則防再犯**：任何超出當期 bound 的「順手做」，必須先在母文件 append 一節改 bound、再動工；commit message 必須引用對應 phase 代號（本期為 `B0`-`B4`）。

## A.3 備選方案（僅當你堅持嚴格歷史潔癖時用，不推薦）

```powershell
# 在 codex/iso-node-workflow-poc 上：
git revert --no-edit 6f9dbdc                       # 產生 revert commit，POC 分支「紙面上」回到 858a7fe 狀態
git switch codex/tauri-react-spike
git merge --no-ff codex/iso-node-workflow-poc      # 主線只收 POC
git switch -c codex/iso-workflow-bridge
git cherry-pick 6f9dbdc                            # 已驗證的工作在新分支原樣復活，commit 訊息保留
```

代價：歷史多兩個對沖 commit、origin 已推出去的 poc 分支歷史與本地分叉（還得 force-push 或留分叉）。**除非有外部稽核需求，不要選這條。**

---

# B. 下一階段總方向：優先序裁決

**裁決順序：5 → 2 → 1 → 4 → 3**

| 順位 | 項目 | 裁決理由 |
|---|---|---|
| 1 | **(5) branch merge / 整理** | 一切的地基。POC 已完成且雙分支都推上 origin，但主線還停在 `ff03fb2`——拖越久 drift 越大、合併越痛。單人開發者最危險的不是分支太少而是「忘記哪條是真的」。先合流、打 tag、清分支，半小時內做完。 |
| 2 | **(2) workflow_run / status / cancel job runner** | 安全模型必須先於任何可以按的按鈕存在。把 allow/confirm 明文傳遞、replay 硬封鎖、取消機制全部在後端定死並測完，之後 UI 想犯錯都沒有路徑。沿用 job dir + polling（與 `start_batch_detect` 同構）——已驗證的模式，零新基礎設施。 |
| 3 | **(1) Read-only workflow inspector UI** | 6f9dbdc 的三個 action + B2 的 run log 讀取，剛好湊成一個零風險的唯讀檢視器（藏在調校 > 進階）。先唯讀後可跑，「安全 > 漂亮」的直接體現；也讓你第一次在 UI 裡看到 graph，提早發現 schema 的呈現問題。 |
| 4 | **(4) 一鍵/工作台/調校接 graph** | 必須等 runner + inspector 證明橋穩了才動，而且**從工作台唯讀消費開始**（顯示 workflow run 的 rows/pilot），一鍵執行路徑最後才換（要 parity test 守門）。本期只做到「工作台能看」，不做「一鍵改走 graph」。 |
| 5 | **(3) React Flow 節點畫布** | 再次明確延後。畫布是把「編輯圖」的能力交給使用者——在 params overlay、guarded 視覺語言、graph 鎖定機制成熟前做畫布，等於把 rename 風險畫成漂亮的按鈕。 |

四模式共用 graph 的終局（維持母文件 §12.3 不變）：一鍵=鎖定模板+hash 釘死、工作台=唯讀 run log、調校=params overlay、節點式=全能力。本期推進到「工作台可唯讀看 workflow run」為止。


---

# C. 下一階段施工書

## 下一階段名稱

**ISO Node Workflow Post-POC Bridge Phase**（代號 `B`；B0 = 已完成的 6f9dbdc）

## 目標（5 個）

1. POC 成果合回 `codex/tauri-react-spike` 主線，打 tag 固定里程碑，收斂到單一工作分支。
2. 後端補齊 workflow job runner：`workflow_run` / `workflow_run_status` / `workflow_cancel` / `workflow_list_runs` / `workflow_read_run_log`，沿用 job dir + polling。
3. 安全模型落地成可測試的程式碼：allow/confirm 每次明文傳遞、replay 對 guarded 硬封鎖、取消可中斷長任務。
4. 調校頁出現唯讀 Workflow Inspector（節點表、validate、run 歷史、side-effect 證據）。
5. Inspector 能執行「safe run」（無 guarded 授權路徑）並輪詢進度、可取消。

## 非目標 / 禁止事項（整期有效）

- 不做視覺節點畫布（React Flow / LiteGraph / Rete.js 一律不裝、不 import）。
- 不做真正 rename：**前端不存在任何能送出 `workflow_allow` / `workflow_confirm` 的程式路徑**；真 rename 仍只能走 CLI 三重門檻。
- 不包 `publish_profile` / `revert_profile` / `save_profile` 成 node 或 action。
- 不改一鍵主流程、不讓一鍵頁變複雜（一鍵相關檔案零 diff）。
- 不新增 side-effect kind、不放寬 AUTO_ALLOWED/GUARDED 分類。
- 不讓 replay 寫入任何 guarded side effect（含經由新 action 的路徑；後端要主動拒絕，不是默默忽略）。
- 不自動重跑 OCR：UI 任何 onChange/useEffect/輪詢路徑禁止呼叫 `workflow_run`；執行只能來自使用者點擊。
- 不重構既有 engine 公開介面；executor 只允許 append-only 加 cancel hook。
- 不動 PyQt legacy、`.qwen/` 永不 stage、不用 `git add -A`。

## Phase 切分（B1–B4，各自獨立 commit、可回滾）

### Phase B1 — 合流與基線整備（git + docs only）

- **目標**：固定 POC 里程碑、合回主線、開出 bridge 分支、把本施工書與母文件 §15 入庫。
- **修改檔案範圍**：僅 `docs/*.md` 與 git 操作；唯一例外是 `git restore` 還原 App.tsx 的空白殘留。
- **步驟（Windows PowerShell，逐行照做）**：
  ```powershell
  cd C:\Users\a0976\Documents\GitHub\桌面輔助系統
  # 0) HEAD 健康檢查（沙箱視圖曾見截斷；Windows 端通常正常）
  git symbolic-ref HEAD          # 期望輸出 refs/heads/codex/iso-node-workflow-poc
  # 若報錯或輸出截斷 → 修復：
  #   git symbolic-ref HEAD refs/heads/codex/iso-node-workflow-poc
  git status --short --branch    # 期望：乾淨，或僅 docs 新檔 + App.tsx 空白差異 + .qwen/ 未追蹤
  git log --oneline -3           # 期望 tip = 6f9dbdc
  # 1) 清掉 App.tsx 空白殘留（若 status 有列出）
  git restore frontend/tauri-spike/src/App.tsx
  # 2) 釘住 POC 完成點
  git tag -a iso-workflow-poc-v1 858a7fe -m "ISO node workflow POC complete (engine+CLI+12 nodes+safe workflow)"
  git push origin iso-workflow-poc-v1
  # 3) 合回主線（--no-ff 保留「這是一包 POC」的歷史形狀）
  git switch codex/tauri-react-spike
  git pull --ff-only origin codex/tauri-react-spike
  git merge --no-ff codex/iso-node-workflow-poc -m "merge(iso-workflow): node workflow poc + readonly bridge (B0)"
  git push origin codex/tauri-react-spike
  # 4) 開 bridge 分支並提交文件
  git switch -c codex/iso-workflow-bridge
  git add docs/iso_pdf_workflow_bridge_phase_plan_2026-06-10.md docs/iso_pdf_node_workflow_codex_handoff_2026-06-10.md
  git commit -m "docs(iso-workflow): record bridge phase plan and poc closure (B1)"
  git push -u origin codex/iso-workflow-bridge
  # 5) 刪除已合併的本地 poc 分支（origin 的留到 B4 合併後再刪）
  git branch -d codex/iso-node-workflow-poc
  ```
- **禁止**：不 rebase、不 squash、不 force-push、不碰任何 `.py`/`.ts`。
- **驗收**：`git log --graph --oneline -10` 看得到 merge commit 與 tag；merge 後在主線跑一次 `python -m pytest tests\test_tauri_iso_workflow.py -q`（或 `-m unittest`）全綠。
- **🟢 Checkpoint**：本 phase 完成即安全停靠點（隨時可交接）。
- **Commit**：`docs(iso-workflow): record bridge phase plan and poc closure (B1)`

### Phase B2 — workflow job runner（backend only）

- **目標**：用「job dir + 子程序 + polling」讓整張 workflow 可被 Tauri 前端啟動/查詢/取消，安全規則全部後端定死。
- **修改檔案範圍**：
  - 新增 `launcher/app/tauri_workflow_job.py`（runner，鏡像 `tauri_iso_worker.py` 的結構，約 150-200 行）
  - 修改 `launcher/app/tauri_iso_workflow.py`（append：5 個 action handler + `IsoWorkflowRequest` 新 optional 欄位 `workflow_inputs` / `workflow_allow` / `workflow_confirm` / `workflow_mode` / `workflow_job_id` / `workflow_run_id`，全部 default None/()）
  - 修改 `launcher/plugins/iso_tools/workflow/executor.py`（append-only：`run_workflow(..., should_cancel: Callable[[], bool] | None = None)`，節點之間檢查；`NodeExecutionContext.should_stop()` 供長節點內部輪詢）
  - 修改 `launcher/plugins/iso_tools/workflow/nodes/detection.py`（batch_detect 輪詢迴圈每圈呼叫 `ctx.should_stop()`，為真時先 `cancel_iso_job` 內層 job 再丟 cancelled）
  - 新增 `tests/test_iso_workflow_job.py`；`tests/test_tauri_iso_workflow.py` append 新 action 測試
- **詳細安全設計見 §E（本文件），照規格實作，不留自由發揮空間。**
- **禁止**：不動既有 21 個 action 與 6f9dbdc 的 3 個 action；executor 既有函式簽名只加 optional kwarg；不引入 streaming/websocket；runner 內不得出現任何「預設放行 guarded」的 fallback。
- **驗收測試**（全部寫進 `test_iso_workflow_job.py`，unittest.TestCase）：
  1. `workflow_run`（monkeypatch spawn → 同步執行）→ job.json 終態 completed、含 run_id/run_dir、`workflow_run_status` 讀得到 per-node 狀態。
  2. 進行中寫 `cancel.json` → run 終態 cancelled、未跑節點 not_run、job.json state=cancelled。
  3. `workflow_mode="replay"` 且 `workflow_allow` 非空 → action 直接 raise（訊息含「replay 不接受 allow」），不產 job dir。
  4. `workflow_allow` 含未知值或 auto 類 → raise。
  5. 圖含 enabled guarded node 且 request 無 allow/confirm → run 完成、節點 blocked、檔案零變動、job.json 的 side_effect_summary 有 blocked 證據。
  6. 帶 allow+confirm 的 `workflow_run` 在 tmp fixtures 上真的 rename（證明後端閘門邏輯與 CLI 等價）——**此測試只存在於後端測試，前端永遠沒有對應 helper**。
  7. 既有回歸：workflow 套件全部測試 + `test_tauri_iso_workflow.py` 全綠。
- **🟢 Checkpoint**：可停靠交接（後端能力完整，UI 未動）。
- **Commit**：`feat(iso-workflow): add workflow job runner bridge actions (B2)`


### Phase B3 — Read-only Workflow Inspector（調校 > 進階）

- **目標**：在調校頁尾加一個預設收合的「進階：節點工作流（唯讀）」區塊，把 graph 與 run 歷史第一次帶進 UI——只能看，不能跑、不能改。
- **修改檔案範圍**：
  - 新增 `frontend/tauri-spike/src/iso/WorkflowInspector.tsx`（單檔元件；型別沿用 6f9dbdc 已放進 `isoWorkflow.ts` 的定義，**不要**另開 types 檔搬家）
  - 修改 `frontend/tauri-spike/src/isoWorkflow.ts`（append：`listIsoWorkflowRuns()`、`readIsoWorkflowRunLog()` 兩個 helper 對應 B2 action）
  - 修改 `frontend/tauri-spike/src/iso/IsoBoard.tsx`（**僅一處**：調校頁尾掛 `<WorkflowInspector />` 的 collapsible 入口）
- **Inspector 內容（全唯讀）**：
  1. 節點型錄：`listIsoWorkflowNodes()` → 表格列 node_type / display_name / inputs / outputs / side-effect chips（auto=黃色「自動允許」、guarded=紅色🔒「需授權」、無=綠色「純讀」）。
  2. 圖檢視：載入 `iso_pdf_safe_poc.workflow.json` → `validateIsoNodeWorkflow()` 結果（issues、topo 順序、推導 edges 數）、disabled 節點灰顯、guarded 節點掛 🔒。
  3. Run 歷史：`listIsoWorkflowRuns()` → 點開單筆顯示 per-node 狀態、`side_effect_summary`（executed/blocked/skipped 分色）、replay 標記。
- **禁止**：沒有任何執行按鈕；沒有任何參數輸入框；不裝新 npm 套件；不動一鍵/工作台分頁；不動 PilotStrip/NamingTable。
- **驗收**：`npx tsc --noEmit` 0 錯；`npm run build` 過；一鍵頁與工作台 git diff = 0；手測截圖（調校頁收合/展開、三個區塊有資料）；`git diff --stat` 僅上列三檔。
- **Commit**：`feat(iso-workflow): add readonly workflow inspector in tuning page (B3)`

### Phase B4 — Inspector safe-run + 輪詢 + 取消

- **目標**：Inspector 可以「安全執行」整張圖：固定無授權（allow/confirm 永遠空）、有進度、可取消、結果含 side-effect 證據。
- **修改檔案範圍**：
  - 修改 `frontend/tauri-spike/src/isoWorkflow.ts`（append helpers，**注意簽名就是安全邊界**）：
    ```ts
    // 刻意沒有 allow/confirm 參數——前端在型別層面就無法授權 guarded side effect
    export function runIsoNodeWorkflowSafe(req: { workflow_path: string; workflow_inputs?: Record<string, unknown> }): Promise<IsoWorkflowJobPayload>;
    export function getIsoWorkflowJobStatus(workflow_job_id: string): Promise<IsoWorkflowJobPayload>;
    export function cancelIsoWorkflowJob(workflow_job_id: string): Promise<IsoWorkflowJobPayload>;
    ```
  - 修改 `frontend/tauri-spike/src/iso/WorkflowInspector.tsx`（執行前 modal、進度列、節點狀態徽章、取消鈕）
- **互動規格**：
  1. 「執行（安全模式）」按鈕 → 先彈確認 modal：列出本圖會發生的 side effects（從 NodeSpec 彙整），enabled 的 guarded 節點標示「🔒 將被阻擋（本介面無授權能力）」→ 使用者確認才送 `workflow_run`。
  2. 進行中：每 800ms 輪詢 `workflow_run_status`，顯示 current_node + percent；輪詢在 unmount/終態時停止。
  3. 「取消」→ `workflow_cancel` → 顯示 cancelled 終態。
  4. 終態：per-node 狀態表 + side_effect_summary；blocked 節點紅框並附一行說明「真實更名僅能透過 CLI 三重門檻執行」。
- **禁止**：`runIsoNodeWorkflowSafe` 以外不得新增任何 run 入口；任何 `useEffect`/`onChange` 內不得出現 `workflow_run`（執行只能在 onClick handler）；不得把輪詢間隔做成可調滑桿（避免重蹈 ROI slider 觸發重跑的覆轍）。
- **驗收**：
  1. safe poc 圖在樣本資料上從 Inspector 跑完，狀態與 CLI run 等價（rows/summary 比對）。
  2. 改一份副本 workflow 把 `apply_rename.enabled=true` → Inspector 跑完顯示 blocked、樣本檔案檔名零變化。
  3. 中途取消 → cancelled、batch_detect 的內層 iso job 也被取消（job.json state=cancelled）。
  4. `grep -rn "workflow_run" frontend/tauri-spike/src/` 的呼叫點全部在 onClick handler 內（人工核對並記進完工回報）。
  5. `npx tsc --noEmit`、`npm run build`、後端測試全綠。
- **🟢 Checkpoint**：本期終點。merge `codex/iso-workflow-bridge` → `codex/tauri-react-spike`（--no-ff），刪 bridge 分支與 origin 的 poc 分支。
- **Commit**：`feat(iso-workflow): run safe workflows from inspector with polling and cancel (B4)`

### B5（預告，不在本期）：工作台唯讀消費 workflow run log → 調校 params overlay → 一鍵 parity 換軌 → 畫布。**Codex 做完 B4 必須停下，等下一份施工書。**

---

# D. Branch / Commit / PR 策略（單人開發者版）

1. **`codex/iso-node-workflow-poc` 要合回 `codex/tauri-react-spike` 嗎？** 要，立刻（B1）。主線停在 `ff03fb2`，POC 六個 commit 都在支線——支線活得越久，你越會搞不清楚「哪條是真的」。合併用 `--no-ff` 留下分組形狀。
2. **858a7fe 當 POC 完成點？** 是，用 annotated tag `iso-workflow-poc-v1` 釘在 `858a7fe`。tag 是「完成點」的正式語言，比「記得那個 commit」可靠。
3. **6f9dbdc？** 保留原地，帳記為 Bridge B0（見 §A）。它會隨 B1 的 merge 一起進主線。
4. **同分支還是新分支？** 新分支，但**一次只活一條**：規則是「主線 `codex/tauri-react-spike` + 至多一條進行中的工作分支」。POC 分支合併後本地即刪。
5. **新分支名**：`codex/iso-workflow-bridge`。
6. **PR/merge 順序**：你是單人 repo，**不需要 PR**——annotated tag + `--no-ff` merge commit 就是你的里程碑記錄。順序：`tag(858a7fe) → merge poc→spike → branch bridge → B1..B4 各一 commit → merge bridge→spike → 刪兩條支線（本地+origin）`。每個 🟢 checkpoint 都可以提前 merge 回主線，merge 越小越安全。若哪天想要 PR 形式的紀錄，再對 merge commit 補 GitHub release note 即可，不必改流程。


---

# E. workflow_run 安全邊界設計（B2 的實作規格，照抄）

## E.1 Request schema（stdin JSON，append-only 欄位）

```json
{
  "action": "workflow_run",
  "workflow_path": "launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json",
  "workflow": null,
  "workflow_inputs": { "work_folder": "C:/Users/a0976/Downloads/t", "combine_pdf": "C:/Users/a0976/Downloads/t/testing.pdf", "iso_list": "C:/Users/a0976/Downloads/t/HP6精準管理.xlsx" },
  "workflow_allow": [],
  "workflow_confirm": [],
  "workflow_mode": "run"
}
```

規則（action handler 內、建 job dir **之前**全部檢查完，違反即 raise，不留半成品 job）：

- `workflow_path` 與 `workflow`（inline graph）二擇一，同 6f9dbdc 的 `_workflow_graph_from_request`；先 load + `validate_graph`，有 error 直接回 validation payload + raise，不開 job。
- `workflow_mode` ∈ {"run", "replay"}；replay 另需 `workflow_run_id`（來源 run），且 **`workflow_allow`/`workflow_confirm` 必須為空，否則 raise**（明確拒絕，不是忽略）。
- `workflow_allow` 元素只接受 `{"renames_files", "writes_profile"}`；出現 auto 類或未知值 → raise（auto 本來就不需要 allow，出現即代表呼叫端誤解了模型）。
- `workflow_confirm` 元素必須是圖中存在且 `requires_confirm` 的 node_id，否則 raise。
- allow/confirm **永不持久化**：不寫 state store、不寫 profile；只進當次 request.json 與 run log 的 policy 區塊（留審計痕跡）。後端沒有任何「記住上次授權」的快取。

## E.2 workflow_job_id 與 job dir

- 產生：`"wfjob-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]`，存回 response；目錄名經 `re.sub(r"[^A-Za-z0-9_.-]", "", job_id)` 消毒（沿用 `_job_dir` 的手法）。
- 位置：`runtime_root()/.runtime/jobs/workflow/<job_id>/`（與既有 `.runtime/jobs/iso/` 並列，永不混放）。內容物：`request.json`（含 allow/confirm 明文）、`job.json`（狀態鏡像）、`cancel.json`（出現即取消）。
- runner 子程序：`subprocess.Popen([sys.executable, "-m", "launcher.app.tauri_workflow_job", str(job_dir)], cwd=Path.cwd(), stdin/stdout/stderr=DEVNULL, creationflags=CREATE_NO_WINDOW)`——與 `_spawn_iso_worker` 同款。runner 內部呼叫 `executor.run_workflow(..., should_cancel=lambda: (job_dir / "cancel.json").exists())`，每個節點結束就原子改寫 `job.json`。

## E.3 Status payload（`workflow_run_status` 回傳；`job.json` 同形）

```json
{
  "schema_version": 1,
  "action": "workflow_job",
  "workflow_job_id": "wfjob-20260610-153000-a1b2c3",
  "state": "running",
  "workflow_id": "iso_pdf_safe_poc",
  "run_id": "wf-20260610-153001-d4e5f6",
  "run_dir": "C:/.../.runtime/runs/workflow/wf-20260610-153001-d4e5f6",
  "progress": { "total_nodes": 8, "done_nodes": 3, "percent": 37, "current_node": "batch_detect", "current_node_percent": 52 },
  "node_states": { "discover": "success", "split": "success", "load_table": "success", "batch_detect": "running" },
  "side_effect_summary": { "executed": [], "blocked": [], "skipped": [], "simulated": [] },
  "error": "",
  "created_at": "…", "updated_at": "…"
}
```

`state` ∈ `queued | running | completed | completed_with_blocked | failed | cancelled | cancel_requested`。`current_node_percent` 來自 batch_detect 轉發的內層 job progress；其他節點為 null。

## E.4 Cancel 鏈

1. `workflow_cancel` action：寫 `cancel.json`，job.json state→`cancel_requested`（與 `cancel_iso_job` 同構）。
2. executor 在**每個節點之間**檢查 `should_cancel()` → 真：當前未開始的節點標 `not_run`，run 終態 `cancelled`。
3. 長節點內部：`batch_detect` 輪詢迴圈每圈呼叫 `ctx.should_stop()` → 真：先對內層 iso job 呼叫 `cancel_iso_job`（不留殭屍 worker），再 raise cancelled。
4. runner 捕捉 cancelled 終態 → job.json state=`cancelled`。取消後 run log 照常 finish（證據完整）。

## E.5 Guarded 防誤觸的縱深（五層）

| 層 | 機制 |
|---|---|
| 1. 圖 | guarded node 預設 `enabled:false`；enabled 而未明寫 `requires_confirm:true` → validate error（WF014） |
| 2. 引擎 | `SideEffectGate`：無 allow → `blocked_policy`；無 confirm → `blocked_policy`；INV-1/2/3 證據鏈 |
| 3. Bridge action | allow 白名單檢查、replay 拒 allow、授權永不持久化 |
| 4. 前端型別 | `runIsoNodeWorkflowSafe` 簽名沒有 allow/confirm 參數——UI「想犯錯都編譯不過」 |
| 5. 流程 | 真 rename 只能 CLI：`enabled:true` + `--allow renames_files` + `--confirm apply_rename` 三因子 |

## E.6 Replay 硬封鎖

- 引擎層已有 `REPLAY_HARD_BLOCKED = {renames_files, writes_profile}`，無旗標可解——bridge 不新增任何繞道。
- bridge 在 action 層**再擋一次**（replay + allow 非空即 raise）：縱深防禦，讓「前端 bug 送錯參數」連引擎都碰不到。
- 測試必含：replay 帶滿 allow/confirm 仍 blocked（引擎測試已有，B2 再加 action 層版本）。

## E.7 UI 提示 guarded node（B3/B4 規格）

- 節點型錄與圖檢視：guarded node 一律紅色🔒 chip +「需 CLI 授權」字樣；disabled 顯示灰色「預設停用」。
- 執行前 modal：列出全部 side effects 分組（將執行/將被阻擋/將跳過），enabled 的 guarded node 顯著標示「🔒 將被阻擋——本介面無授權能力」。
- 結果頁：blocked 節點紅框 + 固定文案「真實更名僅能透過 CLI 三重門檻執行」。UI 永遠不出現「授權」「解鎖」按鈕。

## E.8 UI 防自動跑 OCR

- Inspector 在 B3/B4 沒有任何參數編輯——參數變更觸發執行的問題在本期根本不存在路徑。
- 鐵則寫死（B4 驗收第 4 條）：`workflow_run` 呼叫只允許存在於 onClick handler；`useEffect` 只允許輪詢 `workflow_run_status`（唯讀）。
- 未來 params overlay 階段沿用既有 ROI debounce 模式（commit `15cf898`）：參數變更只更新草稿 state，執行永遠是顯式按鈕。本期不實作，只把規則寫進母文件 §15。

---

# F. 母文件（handoff MD）修正

裁決：以 **append-only 新增 §15** 處理（符合本專案「P01-P12 凍結、其後 append」的一貫精神），§13 原文不改字、由 §15 宣告其「對 POC 期封存」。**§15 全文已由本次作業直接寫入** `docs/iso_pdf_node_workflow_codex_handoff_2026-06-10.md` 尾端（內容＝完成點宣告、6f9dbdc 定位、Bridge phase plan 指針、已知風險、下一個 Codex 指令），B1 把它與本施工書一起 commit。若需人工核對，§15 開頭為「## 15. POC 收尾裁決與 Bridge Phase 銜接（2026-06-10 架構審查）」。

---

# G. 最終明確建議

- **現在應該停在 commit**：`6f9dbdc`（= `codex/iso-node-workflow-poc` tip，不回退）；POC 里程碑 tag 打在 `858a7fe`（`iso-workflow-poc-v1`）。
- **6f9dbdc 應該**：**保留**（追認為 Bridge Phase B0；不 revert、不拆分）。
- **下一個分支應該叫**：`codex/iso-workflow-bridge`（從合併後的 `codex/tauri-react-spike` 開出）。
- **下一個 Codex 要做的第一件事**：執行 Phase B1 的 PowerShell 步驟 0-5（驗 `git symbolic-ref HEAD` 與 `git status` → 還原 App.tsx 空白殘留 → tag `iso-workflow-poc-v1` → `--no-ff` merge poc→spike → 開 `codex/iso-workflow-bridge` → commit 本施工書 + 母文件 §15）。
- **下一個絕對不能做的事**：給前端任何能送出 `workflow_allow` / `workflow_confirm` 的程式路徑（包含「先寫好之後再藏起來」）——本期 UI 的執行能力上限就是 safe run；同理，任何 onChange/useEffect 觸發 `workflow_run` 或 OCR 一律禁止。

> Codex 收到本文件後：不需要再提問。從 §C Phase B1 開始，照 phase 順序施工，每個 phase 一個 commit，B2/B4 結尾的 🟢 checkpoint 可停下交接。B4 做完必須停，等下一份施工書。
