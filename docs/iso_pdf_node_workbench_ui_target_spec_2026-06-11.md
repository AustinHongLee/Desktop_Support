# ISO PDF Node Workbench Fable 5 UI Target Spec

> Date: 2026-06-11
> Base: `codex/tauri-react-spike` @ `ae0960d`（E 期已完成 merge `191de25` + tag `iso-workflow-e-v1`；其後有兩個直接上主線的 UI commit：`4511ae2` 修畫布可見性、`ae0960d` 加了 664 行流程樹——後者就是本文件要矯正的方向）
> 施工分支：`codex/iso-node-workbench`（workbench 工作回到分支紀律，不再直接 commit 主線）
> 本文件性質：產品目標 + UI 心智模型 + 可施工可驗收的下一階段規格。引用的元件/函式/行號都對照 `ae0960d` 實碼驗證過。

---

## 1. Product Definition

「節點式」不是第 4 個功能，也不是 graph viewer。它是 ISO PDF 工具裡**一鍵、工作台、調校三大功能的合併表達**：同一條資料流（PDF → 拆頁 → ISO 清單 → ROI/參數 → 批次判讀 → Pilot 檢查 → 匯出 → 更名），用 ComfyUI / Blender Geometry Nodes 式的節點畫布呈現，讓使用者**一眼看懂資料從哪來、被什麼參數影響、流到哪去**，並且能在節點上直接看資料、調參數、重跑。

判斷標準一句話：打開節點式分頁，看到的應該是「一個可執行的節點工作台」，而不是「一份工程報表」。

## 2. Current Problem（寫給 Codex 的明確矯正清單）

`WorkflowInspector.tsx`（`ae0960d` 後 2000+ 行）目前的主體是垂直堆疊的 sections：`流程樹`（L518，ae0960d 加的 664 行 step tree + EvidenceCard）→ `節點型錄`（L585）→ `工程 DAG`（L608，畫布被塞在一個 section 裡）→ `執行紀錄` 表格（L690）→ `換軌守門`（L742）。這是工程 debug 頁，不是 node workbench。逐條矯正：

1. **不要再把主畫面做成流程樹**。ae0960d 的 step tree 是好的 debug 工具、錯的位置——整段降級進底部摺疊抽屜，不准佔主視覺。
2. **不要把主畫面做成表格報表**。執行紀錄表、節點型錄表全部進抽屜。
3. **不要把 node catalog / topology / graph JSON 當主體**。
4. **ReactFlow 畫布必須是主角**：進分頁第一眼就是大畫布，不是 section 之一。
5. **節點本體要承載資料**：現在的 `WorkflowCanvas.tsx` 節點卡只有名稱+狀態 chips；要升級成有摘要數據、預覽、操作鈕的模組卡。
6. **線要真的接起來**：現在每個節點只有左右各一個 `Handle`（L92/L104），所有邊都糊在同一點上，看起來像散落卡片。必須改成 **per-port labeled handles**（`Handle id=port 名`），邊連到正確的 port。
7. Debug 資料（step tree、run log JSON、graph JSON、catalog、gate）保留，但**預設收合**在底部抽屜。

## 3. Correct Mental Model

```text
使用者心智：「我把 PDF 丟進左邊，東西沿著線往右流，每個節點是一站；
            站上看得到結果摘要，點開看細節，改了參數就亮黃燈，按重跑才會動。」

畫布資料流（左 → 右）：
[PDF 來源] ──combine_pdf──▶ [拆頁 PDF] ──pages──▶ ┌──────────────┐
[PDF 來源] ──work_folder─▶ [ISO 清單] ──iso_rows─▶ │  批次判讀     │──rows──▶ [Pilot 檢查]
[ROI 調校] ──serial_region/drawing_region/threshold/detect─▶ │ (OCR/Vision) │──rows──▶ [信心分布]
                          [ROI 調校] ──pattern? 見 §6──────▶ └──────────────┘──rows──▶ [匯出 CSV]
                                                                              ──rows──▶ [套用更名]
```

三大功能映射：**一鍵** = 工具列「執行整張圖」+ 節點狀態燈；**工作台** = 節點卡摘要 + 右側詳情面板（rows/Pilot/分布）；**調校** = ROI/ISO/參數節點的可編輯欄位 + dirty 重跑模型。

## 4. Node Canvas Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 工具列：▶ 執行整張圖 │ ⏹ 取消 │ 執行狀態/進度 │ run 選擇器(最近) │ 引擎chip │
├──────────────────────────────────────────────┬──────────────────────┤
│                                              │  選取節點詳情面板      │
│            ReactFlow 大畫布（主角）            │  (360-420px, 可收)    │
│   佔滿剩餘空間，min-height 65vh                │  依節點類型渲染        │
│   per-port handles、真連線、狀態邊框            │  （§7 各節點詳情）     │
│                                              │                      │
├──────────────────────────────────────────────┴──────────────────────┤
│ ▸ 工程檢視（預設收合抽屜）：流程樹 / 執行紀錄 / 節點型錄 / 換軌守門 /     │
│   graph JSON / run log JSON                                          │
└─────────────────────────────────────────────────────────────────────┘
```

- 畫布高度：取代現在 `clamp(520px, 58vh, 760px)` 的 section 內嵌寫法，改為 flex 填滿（toolbar 與抽屜之外的全部）。
- 節點狀態視覺：成功=綠邊、執行中=藍邊+轉圈、失敗=紅邊、dirty=琥珀邊+「參數已變更」badge、disabled/guarded=灰底+🔒（沿用 C4 鎖定語言）。
- 邊：`MarkerType.ArrowClosed`（已有）、執行中資料流的邊可亮色（成功後恢復）。

## 5. Node Types and Responsibilities（畫布節點 ≠ 引擎節點，映射如下）

**關鍵架構裁決**：畫布是「呈現圖」，由引擎圖（`iso_pdf_safe_poc.workflow.json` 的 8 個引擎節點）+ **2 個 UI 合成節點**組成。合成節點把 `$workflow.inputs.*` 變成看得見的來源站，引擎圖與 schema **零修改**：

| 畫布節點 | 對應 | 說明 |
|---|---|---|
| 1. PDF 來源（PDF Source） | 合成節點 ⊕ 引擎 `discover` | 持有 workflow inputs：work_folder/combine_pdf；顯示 discover 的探索結果 |
| 2. 拆頁 PDF（Split PDF） | 引擎 `split` | side effect: may_write_page_pdfs（auto） |
| 3. ISO 清單（ISO List） | 引擎 `load_table` | sheet/欄位參數可調 |
| 4. ROI 調校（ROI / Calibration） | 合成節點（inputs: serial_region/drawing_region/confidence_threshold/detect_serials/pattern） | 內含單頁預覽 + ROI 框 + dirty 模型 |
| 5. 批次判讀（Batch Detect） | 引擎 `batch_detect` | writes_job_files / writes_iso_run_log / spawns_worker（auto） |
| 6. Pilot 檢查（Pilot Checks） | 引擎 `pilot` | P01-P15 |
| 7. 信心分布（ROI Distribution） | 引擎 `roi_dist` | 純讀 |
| 8. 匯出 CSV（Export CSV） | 引擎 `export_csv`（disabled/guarded）⊕ 既有手動匯出 action | 卡片按鈕走 §10 的受認可路徑 |
| 9. 套用更名（Apply Rename） | 引擎 `apply_rename`（disabled/guarded）⊕ 既有 `apply` action | 同上 |

## 6. Ports and Data Flow（handle id 命名 = 下表 port 名，邊按 port 對接）

```text
pdf_source:   out: combine_pdf, work_folder, page_folder_hint
split_pdf:    in:  combine_pdf, work_folder          out: page_folder, pages, pdf_count
iso_list:     in:  work_folder, iso_list             out: iso_rows, iso_source, sample_records
roi_calib:    in:  page_sample(來自 split.pages 首頁)  out: serial_region, drawing_region,
                                                          confidence_threshold, detect_serials, pattern
batch_detect: in:  pages, iso_rows, serial_region, drawing_region,
                   confidence_threshold, detect_serials, pattern
              out: rows, job, iso_run_log
pilot:        in:  rows                              out: pilot_results, pilot_summary
roi_dist:     in:  rows, confidence_threshold        out: distribution
export_csv:   in:  rows                              out: csv_path
apply_rename: in:  rows                              out: rename_result
```

實作對應：合成節點的 out-port 值=workflow inputs overlay（`buildWorkflowInputsOverlay`，helpers.ts 既有）；引擎節點的 in-port 邊由 `flowAdapter` 從引擎圖 refs 推導（既有）+ 新增「inputs ref → 合成節點 port」的邊推導。`pattern` 歸 ROI 調校節點輸出（命名規則屬判讀參數組）。


## 7. Node Card Content（卡上摘要 vs 詳情面板 vs 之後再接）

資料來源欄位約定：**卡上** = 最近一次 run 的投影/artifact 摘要 + 即時 job 狀態；**詳情** = 點選節點後右側面板；**之後** = MVP 不做、規格先留。

| 節點 | 卡上（第一階段，文字摘要為主） | 詳情面板（重用既有元件） | 之後再接 |
|---|---|---|---|
| PDF 來源 | combine PDF 檔名、work folder 短路徑、「已找到拆頁資料夾 ✓/✗」、PDF 頁數/檔數 | 來源選擇按鈕（重用 `pickIsoCombinePdf`/`pickIsoWorkFolder`）、discover 候選清單 | 首頁縮圖（`loadIsoPreview` 單頁即可先做進詳情） |
| 拆頁 PDF | 狀態、page folder 短路徑、page count、side-effect chip | 前 8 頁檔名列表；「重新拆頁」鈕 | 頁面 thumbnails 格 |
| ISO 清單 | xlsx 檔名、sheet 名、row count、serial/line 欄位字母 | sheet 下拉 + 欄位選擇（重用 `loadIsoTable` 流程）、sample rows 前 5 列 | — |
| ROI 調校 | threshold 值、detect_serials on/off、pattern、ROI 兩框座標摘要、**dirty badge** | **單頁 PDF 預覽 + ROI 框**（重用 `RoiOverlay`（props: serialRegion/drawingRegion/editable/onChange）+ `loadIsoPreview` 既有 debounce）、serial/drawing crop 預覽（`IsoPreviewPayload.serial_crop`）、threshold slider、「套用並重跑判讀目前頁」「重跑下游」 | 多頁取樣預覽 |
| 批次判讀 | 進度條（job percent）、total/success/低信心/未判讀 計數、job_id 短碼、side-effect chips | rows 樣本表（重用 `NamingTable` readOnly 或 `WorkflowRunPlanPanel fixedRunId`）、「一鍵判讀」「取消」「重跑此節點」「重跑下游」 | 失敗列快速跳轉 |
| Pilot 檢查 | P01-P15 計數膠囊（ready/warn/blocked）、blocks_apply 警示 | `PilotListPanel`（props: items/onJump/showEngineerDetail）完整清單、「重新檢查」 | 問題列跳至判讀詳情 |
| 信心分布 | 高/低/未判讀三段條、threshold 標線值 | `RoiSamplePanel`（props: distribution/rows/threshold）、低信心樣本列、「跳回 ROI 調校」（選取 roi_calib 節點）、「重跑判讀」 | 直方圖 |
| 匯出 CSV | 狀態 chip（引擎節點=停用·guarded🔒）、上次匯出路徑+列數 | 「匯出草稿 CSV」鈕（走 §10 受認可路徑）、匯出歷史最近 3 筆 | — |
| 套用更名 | ready/blocked 計數、引擎節點=停用·guarded🔒、上次套用筆數 | 更名清單預覽（selected rows 對照表）、「套用更名」鈕（§10 既有確認流） | dry-run diff 視圖 |

計數來源（全部既有，不需新後端）：rows/summary 來自 `workflow_plan_from_run` 投影；低信心=rows 中 `confidence < threshold` 且非空；未判讀=`serial` 空；Pilot=投影 `pilot_results`；分布=`loadIsoRoiDistribution(rows)`；job 即時=`workflow_run_status.node_states` + `current_node_percent`。

## 8. Interaction Model

1. **選取**：點節點 → 右側詳情面板切換至該節點；再點空白 → 收合。畫布可拖動節點（位置不持久化，MVP 接受）。
2. **參數編輯**：只發生在 PDF 來源/ISO 清單/ROI 調校三個節點的詳情（與卡上少量控件）。任何參數變更：(a) 寫入本地 overlay state；(b) 該節點與其下游全部標 **dirty**（琥珀邊 +「參數已變更，尚未重新判讀」）；(c) **絕不自動執行**。
3. **執行**：工具列「執行整張圖」（= 既有 `runIsoNodeWorkflowSafe` + overlay inputs）；節點卡「重跑此節點」「重跑下游」（§9）。執行中：工具列顯示目前節點與 percent；節點依 `node_states` 亮燈；「取消」走既有 `cancelIsoWorkflowJob`。
4. **完成**：dirty 清除、各卡摘要刷新（重新拉投影/artifact）、邊恢復常色。
5. **錯誤**：失敗節點紅邊；詳情面板頂部顯示人話錯誤（E4 的 failed_node 對照文案直接重用）+「重試」。
6. ROI slider/拖框：只動 overlay + 既有 debounced 單頁預覽（`loadIsoPreview`，15cf898 行為），**昂貴判讀永遠等使用者按鈕**。

## 9. Runtime / Re-run Model

| 動作 | 後端 | 現況 |
|---|---|---|
| 執行整張圖 | `workflow_run`（safe，allow/confirm 恆空）+ 輪詢 + 取消 | ✅ 既有（E 期） |
| 重跑單一節點 | **新增 action `workflow_run_node`**：包既有 `executor.run_single_node(source_run_dir, node_id, …)`（L347，已支援 should_cancel/on_update→直接接 job runner 模式），上游輸入自最近一次 run 的 artifacts hydrate | 🔧 本期新增（薄包裝） |
| 從某節點重跑下游 | **新增 executor `run_from_node(source_run_dir, start_node)`**：start 的上游節點全部 hydrate 為快取結果（status=hydrated），start+下游按拓撲重新執行；包成 action `workflow_run_from` | 🔧 本期新增（引擎 append-only） |
| dirty 與重跑的關係 | 「重跑下游」的起點 = 最上游的 dirty 節點；合成節點 dirty（ROI/ISO/PDF 來源）→ 起點為其第一個引擎下游（如 batch_detect） | UI 規則 |

三個執行入口全部沿用 job dir + polling 模式（`tauri_workflow_job` 增 mode 分支），safe mode 硬編碼，cancel 鏈沿用。**沒有 run 歷史時**：卡片顯示「尚未執行」，單節點/下游重跑按鈕 disabled（沒有可 hydrate 的上游），只有「執行整張圖」可按。

## 10. Safety Model（一條都不能鬆）

1. **畫布永遠跑 safe mode**：三個執行 action 的 allow/confirm 由後端硬編碼為空；前端 helper 簽名無此參數（沿用既有靜態守門測試）。
2. **Export / Apply 的「可操作」不等於解鎖引擎 guarded 節點**——這是本規格的基石裁決：
   - 引擎圖中 `export_csv`/`apply_rename` 維持 `enabled:false`+guarded，卡片如實顯示「引擎節點：停用 ·🔒guarded」。
   - 卡片上的「匯出草稿 CSV」按鈕 → 呼叫**既有手動匯出** `exportIsoPlanCsv`（C2 路徑：預設 `.runtime/exports/iso/`、retention、Excel 鎖檔中文錯誤）——這本來就是受認可的使用者明示動作。
   - 「套用更名」按鈕 → 呼叫**既有** `applyIsoPlan`（既有確認對話框 + `_validate_operations` + B11 record artifact + run log）——與一鍵/工作台同一條安全路徑。
   - 因此：UI 上 guarded 能力可用，但執行走的是早已存在、有確認、有審計的 action；workflow 引擎的 guarded 封鎖、replay 硬封鎖、policy 三集合**零變化**。靜態守門測試加一條：workbench 程式碼不得出現 `workflow_allow|workflow_confirm`，`applyIsoPlan` 呼叫點必經確認對話框元件。
3. dirty/slider 永不觸發執行（grep 守門：useEffect/onChange 禁 run 字串，沿用既有測試擴充範圍到 workbench 檔案）。
4. 防污染契約不變：safe 圖照舊不產 CSV；手動匯出走 C2 預設路徑。pollution suite 每步照跑。
5. E 期 engine flag / breaker / audit 不受影響（workbench 不讀寫 one-click engine flag；一鍵分頁行為零變化）。

## 11. MVP Scope

必含（=第 16 節驗收項）：ReactFlow 大畫布為主體；10 個畫布節點 + per-port 真連線；每卡有資料摘要；Batch/ROI/Pilot 卡有核心數據；Export/Apply 安全狀態清楚＋受認可按鈕可用；點選節點 → 右側詳情（重用既有元件）；工程 debug 全部收進預設收合抽屜；整圖執行/取消/單節點重跑/下游重跑 + dirty 模型；不破壞任何既有安全與測試。

## 12. Non-Goals（MVP 明確不做）

完整自訂 workflow 編輯器；任意新增/刪除節點；拖拉接線與佈局持久化；完整圖像編輯器；取代一鍵/工作台/調校分頁（三分頁原樣保留）；多 workflow 模板切換；節點動畫美化。


## 13. Implementation Plan for Codex（W1-W7，每步一 commit）

> 先回答「要不要 revert」：**不 revert**。`4511ae2`（畫布可見性修復）保留；`ae0960d` 的 664 行流程樹是好的 debug UI、錯的位置——W1 把它**整段搬進**底部抽屜，不刪功能。但紀律修正：這兩個 commit 直接上了主線，workbench 起所有工作回到分支 `codex/iso-node-workbench`。

### W1 — 版面翻轉：畫布成為主角（frontend）
- 新增 `frontend/tauri-spike/src/iso/workbench/NodeWorkbench.tsx`（工具列+畫布區+右側面板槽+底部抽屜的版面骨架）；修改 `WorkflowInspector.tsx`：節點式分頁主體改 render `<NodeWorkbench>`，把現有 五個 sections（流程樹/節點型錄/工程 DAG 包的舊畫布/執行紀錄/換軌守門）原封搬進底部「工程檢視」抽屜（預設收合）。`IsoBoard.tsx` 不動（仍 mount WorkflowInspector）。
- 驗證：`npx tsc --noEmit; npm run build`；手開節點式分頁：第一眼=大畫布（先沿用既有 WorkflowCanvas 渲染），抽屜收合。
- Commit：`feat(iso-workbench): canvas-first layout with collapsed engineering drawer (W1)`

### W2 — 呈現圖 + per-port 連線（frontend）
- 修改 `flowAdapter.ts`：新增 `buildWorkbenchGraph(validationPayload, overlayInputs)` → 在引擎 8 節點外合成 `pdf_source`/`roi_calib` 兩節點；依 §6 port 表產出 per-port edges（含 `$workflow.inputs.*` ref → 合成節點 port 的邊）；分層佈局沿用拓撲 x 分層。`flowAdapter.test.ts` append：合成節點存在、邊數與 §6 一致、port id 正確、round-trip 不變。
- 修改 `WorkflowCanvas.tsx`：節點卡改多 `Handle`（每 port 一個，`id=port 名`、左 in 右 out、旁標 port label 小字）；邊 `sourceHandle/targetHandle` 對接。
- 驗證：`npm run test:unit` 新測試綠；畫布上每條線兩端落在具名 port。
- Commit：`feat(iso-workbench): presentation graph with per-port wiring (W2)`

### W3 — 資料上卡 + 詳情面板（frontend，本步最大）
- 新增 `workbench/nodeCards.tsx`（各類型卡內容，§7 卡上欄）與 `workbench/NodeDetailPanel.tsx`（§7 詳情欄；重用 `RoiOverlay`/`RoiSamplePanel`/`PilotListPanel`/`NamingTable`/`WorkflowRunPlanPanel fixedRunId`/`loadIsoPreview`）。資料來源：最近 run（`listIsoWorkflowRuns` 取最新 → `loadIsoWorkflowPlanFromRun` + `readIsoWorkflowArtifact`）+ 執行中 `workflow_run_status.node_states`。無 run → 各卡顯示「尚未執行」。
- 驗證：tsc/build；fixtures 跑一次整圖後手測：Batch 卡見 total/success/低信心、Pilot 卡見 P 計數、ROI 詳情見預覽+框。
- Commit：`feat(iso-workbench): node cards with data summaries and detail panel (W3)`

### W4 — 參數與 dirty 模型（frontend）
- overlay state 掛 `NodeWorkbench`（重用 `buildWorkflowInputsOverlay` 邏輯）；PDF 來源/ISO 清單/ROI 調校詳情可編輯；變更 → 自身+下游 dirty（琥珀邊+badge）；slider 僅動 overlay+既有 debounced 預覽。`test_frontend_safety_contract.py` append：workbench 檔案 useEffect/onChange 禁 `workflow_run|runIso.*Workflow|startIsoBatchDetect`。
- 驗證：tsc/build + 守門測試；手測拖 slider 20 下 DevTools 零執行請求。
- Commit：`feat(iso-workbench): editable params with dirty propagation (W4)`

### W5 — 單節點 / 下游重跑（backend + frontend）
- Backend append：`executor.run_from_node(source_run_dir, start_node, …)`（上游 hydrate、start+下游重執行；append-only 新函式）；`tauri_workflow_job` 增 `run_node`/`run_from` 模式；actions `workflow_run_node`/`workflow_run_from`（safe 硬編碼、job dir 模式、job_id 輪詢取消沿用）；`tests/test_iso_workflow_rerun.py`（hydrate 正確、下游全重跑、guarded 節點在重跑中依然 blocked、cancel、無 source run 時拒絕）。
- Frontend：卡片「重跑此節點/重跑下游」接新 helpers（onClick 唯一呼叫點，靜態守門 append）；dirty 起點規則（§9）。
- 驗證：`python -m pytest tests\test_iso_workflow_rerun.py tests\test_iso_workflow_job.py tests\test_tauri_iso_workflow.py -q` + 前端三件套。
- Commit：`feat(iso-workflow): single-node and downstream rerun (W5)`

### W6 — Export / Apply 受認可路徑 + 安全視覺（frontend 為主）
- Export 卡按鈕 → `exportIsoPlanCsv`（rows 來自最近投影）；Apply 卡按鈕 → 既有確認對話框流程 → `applyIsoPlan`；兩卡 guarded/disabled 視覺照 §10；`test_frontend_safety_contract.py` append（workbench 禁 allow/confirm 字串、apply 必經確認元件）；pollution suite 照跑。
- 驗證：`python -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q` + 前端三件套；手測：匯出落 `.runtime/exports/iso/`、apply 在樣本副本上走完整確認。
- Commit：`feat(iso-workbench): sanctioned export and apply with guarded visuals (W6)`

### W7 — 驗收打勾 + 收尾（docs + merge）
- 跑 §15 全矩陣；對 §16 checklist 逐項打勾（截圖一張全景）；本文件 append 完工 postscript；merge `--no-ff` 回 `codex/tauri-react-spike` + tag `iso-workbench-v1`。
- Commit：`docs(iso-workbench): record workbench completion (W7)`

**全期不能碰**：一鍵/工作台/調校三分頁行為與檔案（`AutopilotView`/`WorkbenchView`/`EngineerView` 零 diff，除非僅 props 透傳）、policy 三集合與 replay 封鎖、E 期 engine flag/breaker/audit、引擎圖 JSON 的節點啟用狀態、Pilot P01-P15、normalize、PyQt legacy、`.qwen/`。

## 14. Suggested File Changes（總表）

| 檔案 | 動作 | 步 |
|---|---|---|
| `frontend/tauri-spike/src/iso/workbench/NodeWorkbench.tsx` | 新增（版面+狀態樞紐） | W1/W3/W4 |
| `frontend/tauri-spike/src/iso/workbench/nodeCards.tsx` | 新增（9 類卡內容） | W3 |
| `frontend/tauri-spike/src/iso/workbench/NodeDetailPanel.tsx` | 新增（詳情面板） | W3 |
| `frontend/tauri-spike/src/iso/WorkflowInspector.tsx` | 重構：主體=NodeWorkbench，舊 sections→抽屜 | W1 |
| `frontend/tauri-spike/src/iso/WorkflowCanvas.tsx` | per-port handles、狀態邊框、卡殼升級 | W2/W3 |
| `frontend/tauri-spike/src/iso/flowAdapter.ts` + `.test.ts` | buildWorkbenchGraph + 合成節點 + port 邊 | W2 |
| `frontend/tauri-spike/src/isoWorkflow.ts` | append helpers：runIsoWorkflowNode/runIsoWorkflowFrom | W5 |
| `launcher/plugins/iso_tools/workflow/executor.py` | append `run_from_node` | W5 |
| `launcher/app/tauri_workflow_job.py` / `tauri_iso_workflow.py` | run_node/run_from 模式 + 兩 action | W5 |
| `tests/test_iso_workflow_rerun.py` | 新增 | W5 |
| `tests/test_frontend_safety_contract.py` | append workbench 守門 | W4/W5/W6 |

## 15. Test / Verification Plan

```powershell
# 每步必跑（前端動到時）
cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit
# 後端動到時（W5）
& .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_rerun.py tests\test_iso_workflow_job.py tests\test_iso_workflow_engine.py tests\test_tauri_iso_workflow.py -q
# 安全回歸（W4/W5/W6 與 W7 收尾）
& .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_pollution.py tests\test_frontend_safety_contract.py -q
# W7 全量
& .venv\Scripts\python.exe -m pytest tests -q          # 期望 0 failed
# 手動煙測（W3/W6/W7 各一次，樣本 C:\Users\a0976\Downloads\t 副本）
```

## 16. Acceptance Checklist（使用者視角，W7 逐項打勾）

- [ ] 打開「節點式」第一眼是大節點畫布，不是樹/表格。
- [ ] 看見 PDF 來源 / 拆頁 / ISO 清單 / ROI 調校 / 批次判讀 / Pilot / 信心分布 / 匯出 / 套用 等節點。
- [ ] 線路按 port 真實連接，一眼讀懂資料流左進右出。
- [ ] 每張卡有該站資料摘要（路徑/計數/狀態），不是只有名字。
- [ ] 點批次判讀：rows / success / 低信心 / job 進度可見。
- [ ] 點 ROI 調校：PDF 預覽 + ROI 框 + threshold + crop 預覽；拖 slider 不觸發判讀，出現 dirty 標記。
- [ ] 點 Pilot：P01-P15 摘要與問題清單。
- [ ] 匯出/套用節點清楚顯示 停用·🔒guarded 與可用的受認可按鈕；套用必經確認對話框。
- [ ] 可執行整張圖、取消、重跑單節點、從節點重跑下游；節點狀態燈即時。
- [ ] Debug JSON / 流程樹 / 執行紀錄 / 換軌守門 全在預設收合抽屜。
- [ ] 全部既有測試 0 failed；pollution + 安全契約綠；一鍵/工作台/調校三分頁零變化。

## 17. Explicit Instructions to Codex

1. 主畫面 = ReactFlow 畫布。流程樹/表格/型錄/JSON 一律進預設收合抽屜——這是硬規則，不是風格偏好。
2. 不 revert 既有 commit；用 W1 的搬移完成矯正。workbench 全部工作在 `codex/iso-node-workbench` 分支，不再直接 commit 主線。
3. 畫布節點=呈現圖（引擎 8 節點 + 2 合成節點），引擎圖 JSON 與 schema 零修改。
4. per-port `Handle`（id=port 名）是 W2 的核心，沒有它就還是散落卡片。
5. 參數變更只標 dirty，執行永遠來自按鈕；slider 沿用既有 debounced 單頁預覽。
6. Export/Apply 按鈕走既有受認可 action（`exportIsoPlanCsv`/`applyIsoPlan` + 既有確認），引擎 guarded 節點維持停用；前端永無 allow/confirm。
7. 每步結束：該步驗證命令全綠 + `git diff --stat` 不越界 + commit + push。卡關就停下寫短報告，不要擴大範圍。

---

## 給 Codex 的短版命令（直接貼）

```text
請讀 docs/iso_pdf_node_workbench_ui_target_spec_2026-06-11.md，它是節點工作台改造的唯一規格。
Pre-flight：cd C:\Users\a0976\Documents\GitHub\桌面輔助系統 → git status 乾淨（.qwen/ 不碰）→ git switch codex/tauri-react-spike && git pull --ff-only → git switch -c codex/iso-node-workbench → 先 commit 本規格文件。
然後照 W1→W7 施工，每步一 commit + push，跑齊該步驗證命令。
鐵則：畫布是主角，debug 全收抽屜；per-port 真連線；節點卡要有資料摘要與預覽；參數改了只標 dirty、執行只能按按鈕；Export/Apply 走既有 exportIsoPlanCsv/applyIsoPlan 與既有確認，引擎 guarded 節點不解鎖；前端永無 workflow_allow/confirm；一鍵/工作台/調校三分頁零變化；既有測試 0 failed。
不做：自訂編輯器、增刪節點、接線保存、取代舊分頁。W7 完成 → merge --no-ff 回 codex/tauri-react-spike、tag iso-workbench-v1、停工回報。
```
