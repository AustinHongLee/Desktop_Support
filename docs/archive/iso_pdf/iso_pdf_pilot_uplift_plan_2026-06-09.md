# ISO PDF 拆頁命名 — Pilot 升級與一鍵 / 工作台 / 調校 redesign 方案

> Date: 2026-06-09
> Branch: codex/tauri-react-spike（base commit 97bb365）
> 範圍：把現有 `pilot.py` 從「run log 診斷資料」升級成「一鍵 / 工作台 / 調校共用的流程導引與衝突檢查系統」，並重做工作台與調校 UI，同時保護一鍵。
> 已讀來源：前端 `iso/*`、後端 `iso_tools/*`、`tauri_iso_workflow.py`、以及 `docs/` 既有設計（audit / blueprint v0.2 / pilot_plan v0.1 / next_stage_design / integrated_execution_plan / 功能落差）。

---

## 0. 一句話總結

**Pilot 不缺，缺的是「被 UI 吃進去」。** `build_pilot_report()` 已經把 `pilot_results` + `pilot_summary` 掛到每一次 `plan` / `build_rename_plan` / batch job 結果上，也寫進 run log、進 debug bundle。但前端目前只有 `RunLogDrawer` 會渲染 pilot（而且讀的是「持久化後的 run log」，不是手上這份 live plan）。`loadIsoPilotReport()` / `pilot_report` action 在前端是死碼。所以本階段主軸是「**消費既有 Pilot**」，不是「再造一套 Pilot」。

---

## 1. 現況診斷

### 1.1 Pilot 資料流（已經存在，但 UI 幾乎沒接）

```
build_iso_plan() / build_rename_plan()
  └─ _with_pilot_results(payload, request)        # tauri_iso_workflow.py:1178
       └─ build_pilot_report(...)                  # pilot.py:27 → items=P01..P12
            payload.pilot_results = items
            payload.pilot_summary = status_counts

tauri_iso_worker.py:217                            # batch job 也會掛 pilot_results
run_log.finish_iso_run_success()                   # run.json 寫入 pilot_results
debug_bundle.export_iso_debug_bundle()             # pilot.json 來自 run.pilot_results
```

前端接收狀況（grep 實證）：

| 來源 | 是否被 UI 使用 |
|---|---|
| `plan.pilot_results`（live，每次 plan/job 都帶） | ❌ **完全沒讀**。`IsoBoard.tsx` 從不引用 `plan.pilot_results` |
| `detail.run.pilot_results`（run log 持久化） | ✅ 僅 `RunLogDrawer` 的 `pilot-mini-list` |
| `loadIsoPilotReport()` / `pilot_report` action | ❌ 前端定義了 wrapper 但**無人呼叫**（死碼） |

結論：後端 P01-P12 端到端可用且已測（`tests/test_iso_pilot.py` 存在），但工作台 / 一鍵主畫面看不到它。這是最大的浪費，也是最低風險的改善點。

### 1.2 兩套平行 checklist，邊界混亂

| 系統 | 位置 | 狀態欄位 | 接到哪裡 |
|---|---|---|---|
| **Pilot P01-P12** | `pilot.py` | pending/running/ready/warn/blocked/skipped | Tauri plan/job/run log/debug bundle（但 UI 只在 run log drawer 顯示） |
| **Autopilot checklist PF/E/W** | `validator.py`（`validate_autopilot_checklist`） | PF01-PF08 / E001-E006 / W001-W003 | **只接到 PyQt legacy**（`iso_pdf_naming_dialog.py`），Tauri 路徑完全沒用 |
| **前端 ChecklistGate** | `AutopilotView` / `WorkbenchView` | 從 row 計數手刻 | 與上面兩套都不同步 |

也就是說目前有三套互不相干的「檢查」語意：後端 Pilot、後端 validator、前端手刻 Gate。`integrated_execution_plan` 第 4.B1 節早已裁決「validator 既有 checklist 是 Pilot List 的子集，不破壞 7 閘門」——但這個收斂在 Tauri 端還沒做。

### 1.3 死碼 / 沒接線的後端能力

- `roi_calibration.py`：`calibrate_serial_roi_from_*`、`confidence_distribution()` 在 **Tauri 路徑與前端都沒被呼叫**。調校的「多頁採樣」目前是 `RoiSamplePanel` 在前端用 `rows[].confidence` 自己算，沒有用到後端的 distribution / 自動校準。
- `pilot_report` action：dispatch 有、wrapper 有，UI 沒用。

### 1.4 三模式邊界是否清楚？

大致清楚，但有滲漏：

- **一鍵**：乾淨。`AutopilotView` 不出現 ROI / 下拉 / JSON。✅ 但導引偏弱——pipeline 卡片是用 `oneClickStage` 粗略推導，不是真正對應 Pilot 哪一關卡住；失敗只有 `FailureCard`，沒有「目前進度 / 是否可繼續」的中間態。
- **工作台**：左欄已有「調校摘要（只讀）+ 跳到調校」(`ReadOnlySetting` + `openEngineerView`)，方向正確。但它另外手刻了一個 `Checklist`（6 個 `Gate`）和 `Issues` 卡片，**和 Pilot 各說各話**；而且 `issueCards` 來自 row 而非 pilot。問題列導航（`chooseProblemRow`）只看 row 狀態，沒有 pilot 的「下一步該去哪個畫面操作」。
- **調校**：參數齊全（sheet/col/pattern/threshold/detect、profile draft/publish/revert）。但**沒有 Pilot List 面板**、沒有「草稿已過期請重生」提醒、ROI 只能單頁、沒有後端 confidence distribution。

### 1.5 UX / 版面問題（對照使用者點名）

- **工作台表格「巨大空白」**：`.iso-table-panel` grid 是 `auto auto auto minmax(0,1fr)`，而 `.workbench-table-stack .iso-table.live { height:100%; }`。當只有 4 筆 row 時，scroll 容器被撐到滿版，4 列擠在頂端、底下一大片空白。需要讓表格容器 `align-content:start` 或不要強制 `height:100%`，改 `max-height` + 自然高度。
- **1181×790**：工作台 3 欄 `minmax(260,340) + minmax(420,1fr) + minmax(260,360)` 最小寬約 940px + gap/padding，在 1181 可塞但偏緊；右欄 inspector 內容多。需在此尺寸與最大化各驗一次（這點我**無法在目前環境截圖驗證**，見 §11）。

---

## 2. 一鍵 / 工作台 / 調校邊界（定稿）

沿用 `integrated_execution_plan` 第 2 節，落到「Pilot 在每層揭露多少」：

| 維度 | 一鍵 Autopilot | 工作台 Workbench | 調校 Engineer |
|---|---|---|---|
| Pilot 呈現 | 只給「人話下一步」：目前在哪關、能不能繼續、卡住要不要交工程師 | Pilot **summary strip** + 問題導航；點 pilot 跳到對應 row/控制 | **完整 Pilot List**（17 項、可展開 `engineer_detail`、auto_fix 按鈕） |
| ROI | ❌ | 只讀框線 + 裁切圖（不可拖） | 可拖框、多頁採樣、distribution |
| 欄位/sheet/pattern/threshold | ❌ | 只讀摘要 + 「跳到調校」 | 可編輯 |
| Profile | 只讀 published 結果 | 只讀標籤 | draft/publish/revert/history |
| Run log / replay / debug bundle | 只在失敗時「匯出問題包 / 交工程師」 | 可開 run log drawer（救援） | 完整 drawer + replay + bundle |
| raw JSON / traceback | ❌ | ❌ | developer mode 才顯示 |

**不該放在工作台、要移到調校的**：ROI 拖框、threshold 滑桿、sheet/col/pattern 編輯、profile publish、raw stack。（工作台目前正確地把這些只讀化了，維持即可；唯一要補的是把手刻 Checklist 換成 Pilot。）

---

## 3. 現有 Pilot P01-P12 對應表（以 `pilot.py` 實作為準）

> ⚠️ 重要：這 12 個 **id / stage 是契約**（已寫進 run.json、debug bundle pilot.json、前端 `pilotLabel` map、`tests/test_iso_pilot.py`）。**不可重新編號。**

| id | stage | 觸發 blocked 的條件 | blocks_apply | 對應 UI 操作位置 |
|---|---|---|---|---|
| P01 | input | 無 work_folder/combine/page | ✅ | 一鍵/工作台來源列 |
| P02 | pdf_source | pdf_count≤0 | ✅ | 來源列 / Combine PDF |
| P03 | split | pdf_count≤0 | ✅ | 來源（重拆） |
| P04 | iso_list | record_count≤0 | ✅ | 調校：ISO List / sheet |
| P05 | mapping | （warn）serial_col/line_col 未定 | ❌ | 調校：欄位對應 |
| P06 | serial_detection | （warn）低信心 / skipped 關閉判讀 | ❌ | 調校：ROI/threshold |
| P07 | iso_correction | 有流水號但找不到 ISO 對應 | ✅ | 工作台：該 row line_no |
| P08 | duplicates | 流水號重複 | ✅ | 工作台：重複 row |
| P09 | missing_serial | 缺流水號 | ✅ | 工作台：缺號 row |
| P10 | naming_pattern | 非法檔名列 | ✅ | 調校：pattern / 工作台 new_name |
| P11 | rename_draft | （warn）尚未產生草稿 | ❌ | 工作台：重新產生 |
| P12 | apply_readiness | blocked_count>0 | ✅ | 工作台：dry-run/套用 |

欄位 schema（每項）：`id, stage, status, user_text, engineer_detail, metrics, auto_fix, manual_hint, blocks_apply, issue_codes`。

---

## 4. Pilot 升級設計（基於現有 pilot.py，不另開平行系統）

### 4.1 P01-P12 夠不夠？要不要擴到 17 項？

**結論：P01-P12 的「正常流程骨幹」夠用；把 17 項當成「append-only 擴充」，而不是「重編號」。**

`next_stage_design` 與 `blueprint v0.2` 都提了 17 項，但它們的 P08-P12 語意和**實作版錯位**（Qwen 版 P08=roi_confidence、P09=duplicate；實作版 P08=duplicates、P09=missing_serial）。若照 Qwen 重編號，會同時打破 run.json、debug bundle、`pilotLabel`、既有測試。所以：

- **凍結 P01-P12 不動。**
- **新增 P13-P17（append-only）**，只放「現有 12 項沒涵蓋」的根因/衝突檢查。優先做 P13-P15：

| 新增 | stage | 角色 | 直接對應使用者點名的衝突情境 |
|---|---|---|---|
| **P13** | `roi_confidence` | 整批 ROI/判讀品質（接上 `roi_calibration.confidence_distribution`） | 影像判讀關閉但流程依賴流水號；ROI 嚴重偏移 |
| **P14** | `profile_consistency` | draft vs published 是否一致、profile 指向的 PDF/ISO/page folder 是否還存在 | Profile draft 與 published 不一致；profile 指向已不存在的檔案 |
| **P15** | `draft_freshness` | 草稿是否過期（ROI/mapping/sheet 改過但未重生；replay 與目前檔案狀態不同） | ROI 改過但草稿未重生；ISO List 換了沿用舊 mapping；run log replay 與現況不同 |
| P16 | `export_log` | CSV / run log / debug bundle 匯出就緒 | （次要） |
| P17 | `apply_safety` | 目標檔已存在 / 檔案鎖定 / rollback 可用（延伸 P12 的「上磁碟」檢查） | （次要，與 P12 互補） |

> 其餘衝突情境已落在現有項目：sheet header 結構不同→P04/P05；OCR 對不上 ISO→P07；target 重複→P08；一鍵可完成但有低信心→P06 warn + 一鍵 review gate。

### 4.2 要不要新增狀態（stale / outdated / needs_review）？怎麼不破壞 schema？

**不新增 enum 值，改用「正交的附加欄位」。** 理由：`_item()` 會對 `PILOT_STATUSES` 做白名單驗證、且舊 run.json / 舊前端建置只認得 6 個狀態；新增 enum 值是 schema break。改成：

```python
# pilot.py 既有 6 狀態維持不變
PILOT_STATUSES = {"pending","running","ready","warn","blocked","skipped"}

# 新增 append-only 附加欄位（皆有安全預設）
_item(... , freshness="fresh",      # "fresh" | "stale"   ← 取代 outdated
           needs_review=False,      # 手動改過未確認
           next_action=None)        # {"label","view","anchor","row_ref"} 結構化下一步
PILOT_SCHEMA_VERSION = 2            # 1→2，純加欄位；讀取端容忍 v1
```

- **stale**：用 `freshness="stale"` 表達（P15 專責產生）。前端把 `freshness==="stale"` 渲染成獨立「過期」徽章，但它**不是** primary status，不會寫進既有 status 統計，因此 `pilot_summary`（6 鍵）不變。
- **needs_review**：row 級「手動改過未確認」→ pilot 層由 P11/P12 帶 `needs_review=true` 並列入 warn。
- 向後相容：舊 run log 沒有這些欄位 → 前端 `item.freshness ?? "fresh"`、`item.needs_review ?? false`。舊前端建置遇到新欄位直接忽略。**雙向相容。**

### 4.3 Pilot 如何產生「下一步建議」與標記 blocks_apply

- **下一步**：每項已有 `user_text`（人話）+ `manual_hint`（操作）+ `auto_fix`（可自動）。升級成結構化 `next_action = {label, view, anchor, row_ref?}`，讓前端能「一鍵跳到正確畫面/控制/列」。第一批可先在**前端**用 `pilotLocation(item)`（依 `stage`/`id` 對照表）推導，後端 payload 不動（最低風險）；後端 `next_action` 列為 P13-P17 落地時一起補。
- **blocks_apply**：維持現有規則（P01/P02/P03/P04/P07/P08/P09/P10/P12）。新增 P14（profile 指向檔案不存在）、P17（目標被鎖）可 block；P13/P15 預設**不** block（只 warn/stale），避免擋住一鍵正常路線。
- 全域 `can_apply = not any(item.blocks_apply and status==blocked)`，與前端 `stateMachine.canApply` 對齊（目前 stateMachine 用 row 計數，升級後改吃 pilot 的 `blocks_apply` 彙總，語意單一真相源）。

### 4.4 Pilot 連結到 UI 實際操作位置

`next_action.view ∈ {autopilot, workbench, engineer}`、`anchor ∈ {source, mapping, roi, pattern, threshold, row, dryrun, profile}`、`row_ref`（如 `page:37`）。前端 `handlePilotJump(item)`：`setIsoView(view)` →（workbench）`setSelectedRowId` + `setProblemOnly(true)` 捲到該列；（engineer）捲到對應 section 並 highlight。

### 4.5 Pilot 如何被 debug bundle / run log / replay 使用

維持現狀並強化：run log 已存 `pilot_results`；debug bundle 已輸出 `pilot.json`。升級後 P13-P17 + 新欄位自動隨之持久化（因為是同一個 `report["items"]`）。**replay** 時，P15 比對「replay 的 `source` / row 狀態」與「目前 request 的檔案/profile」→ 若不同則 `freshness="stale"`，在工作台頂端提示「此為回放結果，與目前檔案可能不同，請重新產生」。

---

## 5. 工作台 redesign（校對與套用主畫面）

版面維持 3 欄（左來源/只讀摘要、中表格、右 inspector），但**用 Pilot 取代手刻 checklist**：

1. **頂部 Pilot summary / progress strip**（新元件 `PilotStrip`）：12（+P13-P15）顆小節點，依 status 著色（✓ ready / ● running / ⚠ warn / 🚫 blocked / ○ pending / ⤺ skipped / ⌛ stale）。資料來源＝`plan.pilot_results`（已存在，免後端改動）。
2. **中間命名草稿表格**：沿用 `IsoPlanTable`。修掉「巨大空白」（§1.5 的 CSS）。列高/欄寬/輸入框在 1181 與最大化都可讀。
3. **問題列視覺語言**（沿用既有 class，補齊對應）：`blocked`（紅左框）、`warn/待確認`（琥珀）、`low-confidence`（琥珀左框）、`missing-serial/missing-line/duplicate`（紅左框）、`manual-corrected`（青左框）、`needs_review`（青框 + 「未確認」徽章，新增）、`ready`（中性）。
4. **右側 PDF visual check 與目前列**：沿用 `IsoVisualPanel`（只讀 ROI）+「目前列」卡。
5. **互動**：`採用判讀值 / 確認此列 / 下一問題` 固定在右側（已存在）。`下一問題`改成「下一個**未通過的 Pilot 或問題列**」循環。
6. **dry-run / 套用入口**：`workbench-apply-strip` 醒目但安全（blocked 永遠禁用，已由 stateMachine 保證）。
7. **調校摘要只讀 + 跳到調校**：保留（`ReadOnlySetting` + `openEngineerView`）。
8. **Pilot 有 blocked/warn 時，直接給下一步**：strip 下方一行「下一步：<pilot.user_text> → [前往修正]」，按鈕走 `handlePilotJump`。
9. 移除與 Pilot 重複的左欄手刻 `Checklist` 6-Gate（改由 PilotStrip 表達），`Issues` 卡片改吃 pilot `issue_codes` + 問題列。

---

## 6. 調校 redesign（完整工程診斷與校準中心）

分層清楚（沿用既有 3 欄，但右欄改成「Pilot List + 診斷」）：

1. **ROI 調整**：保留拖框（`RoiOverlay`）。新增**切頁採樣**：可選第 N 頁載入預覽（目前只看 selectedRow）。
2. **流水號 ROI / 圖號 ROI 分區**：`IsoVisualPanel` 的 segmented（已有），調校時 `editableRoi`。
3. **多頁採樣 / distribution**：接上後端 `confidence_distribution`（新增 action `roi_distribution`），取代純前端估算；顯示 高/低/未判讀 + 最弱頁清單（`RoiSamplePanel` 升級資料源）。
4. **欄位 mapping / sheet / serial_col / line_col / pattern**：保留 `EngineerView` 表單。
5. **confidence threshold / OCR 狀態**：保留滑桿；OCR 狀態（cv2/rapidocr）改吃 P06/P13 的 metrics（目前前端沒顯示安裝狀態）。
6. **Profile draft / published / revert / publish**：保留（已完整）。
7. **Pilot List drawer / panel**（新元件 `PilotListPanel`）：17 項全展開、每項顯示 `engineer_detail`、`metrics`，`auto_fix`/`manual_hint` 變成可點按鈕（auto_fix → 觸發對應 action；manual_hint → `handlePilotJump`）。
8. **Run Log / Replay / Debug bundle**：保留 `RunLogDrawer`。
9. **「草稿已過期，請重生」**：P15 `freshness==="stale"` → 調校頂部黃條 + 「重新產生草稿」。觸發點：ROI/threshold/sheet/col/pattern 任一改動且已有 plan。
10. **回流工作台與一鍵**：調校改完 → `save_draft_profile`（已自動，debounce 650ms）→「發布到一鍵」`publish_profile`（已有）。發布後一鍵下次讀 published。

---

## 7. 一鍵導引補強（要導引，但不工程化）

`AutopilotView` 只吃 pilot 的「人話投影」，**不出現 ROI/下拉/JSON**：

- **首頁顯示進度**：pipeline 6 卡維持，但每張卡狀態改由「對應的 pilot 群組」推導（來源=P01-P03、判讀=P06、對 ISO=P04/P07、命名=P10/P11、更名=P12），而非只看 `oneClickStage`。
- **執行中顯示目前 Pilot**：標題列加一行「正在：判讀流水號 38/42」←來自目前 `running` 的 pilot `user_text` + job progress。
- **成功後**：用 `pilot_summary` 給「X 可更名 · Y 已確認」摘要（人話），不列 P 代號。
- **失敗後「交給工程師」**：沿用 `FailureCard`（複製/匯出問題包/開工作台），再加一行 pilot 推導的「最可能原因」＝第一個 `blocked` 項的 `user_text`。
- **能不能繼續**：依 `blocks_apply` 彙總給「可以繼續 / 需先處理 N 項」一句話 + 單顆主按鈕（已有 `oneClickButton`）。
- **診斷包 / run log / 跳工作台或調校**：只在 review/failure 時出現入口（不放在正常成功路徑）。

---

## 8. 分階段實作計畫（append-only，先保護一鍵）

| Batch | 內容 | 後端/前端 | 風險 | 可驗證手段 |
|---|---|---|---|---|
| **1. Pilot 型別 / helper / 對齊** | 前端 `IsoPilotItem` 加 `freshness?/needs_review?/next_action?`（皆 optional）；helpers 加 `pilotIcon/pilotTone/pilotLocation/pilotNextStep`；新增共用 `PilotStrip` + `PilotListPanel` 元件（先不掛進畫面）；後端 pilot.py 加附加欄位（預設值）+ schema v2。**不改任何既有行為。** | 前端為主 + 後端純加欄位 | 極低 | `npm run build`（=`-Suite frontend`）；`tests/test_iso_pilot.py` |
| **2. 工作台 Pilot summary + 問題導航** | `WorkbenchView` 掛 `PilotStrip`（吃 `plan.pilot_results`）；`handlePilotJump`；移除手刻 6-Gate；修表格「巨大空白」CSS；`needs_review` 徽章 | 前端 + CSS | 低（只動工作台） | `npm run build` + UI 截圖（使用者端） |
| **3. 調校 Pilot List + 校準** | `EngineerView` 掛 `PilotListPanel`；P15 stale 黃條；後端新增 P13/P14/P15 + `roi_distribution` action；`RoiSamplePanel` 改吃後端 distribution；切頁採樣 | 前端 + 後端 | 中（新增 pilot 項目 / action） | `npm run build` + `test_iso_pilot.py`（擴充）+ UI |
| **4. 一鍵輕導引 / 失敗橋接** | pipeline 卡狀態改吃 pilot 群組；執行中「正在 Pxx」一句話；成功/失敗 pilot 投影。**不改一鍵主流程與按鈕語意。** | 前端 | 中（碰一鍵，需特別小心） | `npm run build` + 一鍵 happy/fail 實測 |
| **5. 測試 / polish** | 擴 `test_iso_pilot.py`（P13-P17、freshness、blocks_apply 彙總）；對齊 `stateMachine` 改吃 pilot blocks_apply；1181×790 與最大化版面微調 | 前後端 | 低 | 全套 + UI 雙尺寸 |

每批一個 commit，建議訊息：
- `feat(iso): add pilot UI types, helpers and shared components`
- `feat(iso): surface pilot summary and issue navigation in workbench`
- `feat(iso): add pilot list panel and P13-P15 calibration checks`
- `feat(iso): wire lightweight pilot guidance into autopilot`
- `test(iso): cover pilot uplift and align apply guards`

---

## 9. 預計修改 / 新增檔案

**新增（前端）**
- `frontend/tauri-spike/src/iso/components/PilotStrip.tsx`（工作台/一鍵摘要條）
- `frontend/tauri-spike/src/iso/components/PilotListPanel.tsx`（調校完整清單）

**修改（前端）**
- `iso/isoWorkflow.ts`（`IsoPilotItem` 加 optional 欄位）
- `iso/helpers.ts`（`pilotIcon/pilotTone/pilotLocation/pilotNextStep/pilotFreshnessLabel`）
- `iso/WorkbenchView.tsx`、`iso/EngineerView.tsx`、`iso/AutopilotView.tsx`、`iso/IsoBoard.tsx`（掛元件 + `handlePilotJump`）
- `iso/stateMachine.ts`（Batch 5：apply guard 改吃 pilot blocks_apply）
- `styles.css`（PilotStrip/Panel 樣式、修表格空白、1181 微調）

**修改（後端）**
- `launcher/plugins/iso_tools/pilot.py`（附加欄位 + P13-P17 + schema v2）
- `launcher/app/tauri_iso_workflow.py`（新增 `roi_distribution` action；P14/P15 需要的 profile draft/published + 檔案存在資訊餵進 `build_pilot_report`）
- `launcher/plugins/iso_tools/roi_calibration.py`（被 `roi_distribution` 呼叫，現成）

**測試**
- `tests/test_iso_pilot.py`（擴充）

**不動**：所有 PyQt6 legacy（`launcher/ui/iso_pdf_naming_dialog.py` 等）、一鍵 backend workflow contract、`validator.py`（保留給 legacy；Tauri 端統一走 Pilot）。

---

## 10. 測試清單

每批至少：
1. `.\scripts\test.ps1 -Suite frontend`（＝`npm run build`＝`tsc && vite build`，型別 + 建置）。
2. 後端 `python -m pytest tests/test_iso_pilot.py tests/test_iso_one_click_workflow.py tests/test_iso_debug_bundle.py`（確認 pilot schema、一鍵、bundle 不破）。
3. Tauri UI 實測（START_HERE > 5 或 `-Suite tauri-ui`）：進 ISO PDF → 用 `C:\Users\a0976\Downloads\t`（testing.pdf + HP6…xlsx）→ 應得 4 ready / 0 warn / 0 blocked：
   - 一鍵：跑到底、終端列出進度、成功摘要正確。
   - 工作台：PilotStrip 12 顆全綠；4 列無「巨大空白」；點 pilot/問題列能跳轉。
   - 調校：Pilot List 可展開；改 ROI 後出現「草稿已過期」；發布/回復正常。
   - **1181×790 與最大化各截一次圖**，檢查列高、欄寬、按鈕、文字可讀。
4. 回歸：一鍵正常路線（happy path）行為與 base 97bb365 一致；故意製造一個 blocked（改壞 pattern）確認 apply 被擋且有下一步。

---

## 11. 風險與回退策略

| 風險 | 緩解 | 回退 |
|---|---|---|
| 動到一鍵穩定線 | Batch 4 才碰一鍵且只加投影、不改按鈕語意/主流程 | 一鍵相關改動獨立 commit，可單獨 `git revert` |
| Pilot 重編號打破契約 | **凍結 P01-P12**，只 append P13-P17 | — |
| status enum break | 不加 enum 值，改正交 `freshness/needs_review` 欄位 + schema v2、雙向相容 | 前端 `?? 預設` 容忍舊資料 |
| stateMachine 改吃 pilot 後 apply 判斷變化 | Batch 5 才改，先確保 pilot blocks_apply 與舊 row 計數等價（測試對拍） | 保留舊計數路徑作 fallback |
| 表格 CSS 改動影響其他畫面 | 只改 `.workbench-table-stack .iso-table.live` scope | 還原該段 |
| 後端新 action 影響 worker | `roi_distribution` 為獨立唯讀 action，不進 worker 流程 | 移除 dispatch 分支 |
| **環境限制**（見下） | — | — |

### 環境限制（必讀，影響「誰來驗證/提交」）

本次協作環境是 Linux sandbox 掛載 Windows repo，實測結果：
- ✅ 可編輯檔案；可跑 `tsc --noEmit`（前端型別檢查，Batch 1 已實測 EXIT 0）；可獨立跑 `pilot.py`（純標準庫，Batch 1 已實測 schema v2 與既有斷言通過）。
- ⚠️ **完整 `npm run build` 在此跑不完**：`vite build` 需平台原生二進位，而 `node_modules/@rolldown` 只有 `binding-win32-x64-msvc`（Windows 版），Linux sandbox 載不起來。型別關（tsc）能過即代表程式碼正確；最終打包請在你 Windows 本機 `-Suite frontend` 完成。
- ⚠️ **檔案工具的「就地編輯」不會即時同步到 Linux 掛載視圖**：新建檔（Write）正常，但 Edit 過的檔在 bash 端可能看到截斷的舊視圖（Windows 權威檔正確）。在此跑 build 前需先把編輯內容重寫到掛載端。
- ❌ **無法 `git commit`**：`.git/index.lock` 存在且不可移除（Operation not permitted）。→「分批 commit」需由你在本機執行（我提供每批檔案清單與 commit 訊息）。
- ❌ **無法執行 `START_HERE.bat`（Windows 批次檔）/ PowerShell `scripts/test.ps1` / 開 Tauri 桌面 UI 截圖**。→ Tauri UI 1181×790 截圖驗證需你在本機完成。

因此建議的落地方式：我在工作樹完成各批程式碼，以 `tsc` + 後端單元測試驗證正確性，你在本機 `-Suite frontend` 跑完整打包、逐批 `git add/commit`、並做 Tauri UI 截圖驗證。
