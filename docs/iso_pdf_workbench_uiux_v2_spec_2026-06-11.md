# ISO PDF Node Workbench — UI/UX v2 設計審查與施工規格

> Date: 2026-06-11
> Base: `codex/tauri-react-spike` @ `fedb2cb`（feat(iso-workbench): render ComfyUI-style rich workflow）
> 現況校準（Codex 2026-06-11 補正）：`fedb2cb` 已經不是舊 10 站小節點圖，而是 React Flow / ComfyUI-style rich workflow 第一版：主畫布已有工作區分叉、ISO/PDF 分支、頁面 placeholder、`P001 ROI 調校 -> 判讀結果 -> 命名合成`、前 10 頁展開限制，以及 ROI 節點本體內的預覽/slider/crop/判讀按鈕。因此本規格不是要求重做方向，而是作為 **v2 精修規格**：統一卡片語言、節點尺寸、線條語意、ROI XL 節點、大量頁面策略與可用性驗收。
> 範圍鐵則：只動 UI/UX 層（`workbench/`、`WorkflowCanvas.tsx`、`flowAdapter.ts` 呈現端）。不改 workflow engine、不改資料契約、不改 guarded policy、不退回 wizard/list。
> 建議施工分支：`codex/iso-workbench-uiux-v2`。若沿用 `codex/tauri-react-spike`，仍須每個 UI phase 小 commit + 驗證 + push，並保留 `.qwen/` 未追蹤不處理。

---

## 0. Codex Current-State Correction

Fable 原稿中對 `fedb2cb` 的部分描述偏向更早的 `WorkflowCanvas.tsx` 小卡版本；實際目前主線已經有 `workbench/WorkflowGuideCanvas.tsx`，且主區已從導覽卡片拉回 React Flow 節點畫布。後續施工請以以下事實為準：

- `WorkflowGuideCanvas.tsx` 是目前節點式主畫布入口；`WorkflowInspector.tsx` 只負責傳入 workflow inputs、preview、run/rerun callbacks 與工程抽屜。
- 主畫布已是 React Flow，可拖曳、縮放、pan；工程 DAG / run log / graph JSON 保留在下方工程檢視。
- 目前已有完整流程骨架：`選取工作區 -> ISO 清單 / 合併 PDF -> 工作表 / 欄位設定 / 命名格式 / 分割工具 -> 頁面 -> ROI 調校 -> 判讀結果 -> 命名合成 -> Pilot -> 匯出 / 套用`。
- ROI 調校已在節點本體內，含 PDF 預覽、`RoiOverlay`、流水號/圖號 ROI slider、信心門檻、裁切預覽與「只更新預覽 / 判讀此頁 / 重跑下游」概念入口。
- 尚未完成的是 v2 品質：節點尺寸分級、狀態語言一致、port 中文顯示、線條資料型別語意、初始 viewport、低信心頁浮上、lazy/LRU 預覽、單頁試判暫存，以及視覺密度打磨。
- UI-1~UI-5 應採「在現有 rich canvas 上精修」，不是刪掉重做，也不是退回 wizard/list。

## 1. 現有 POC 的 UI 問題清單

### 1.1 非工程使用者視角（按嚴重度排序）

| # | 問題 | 證據/位置 | 影響 |
|---|---|---|---|
| 1 | **不知道從哪開始、現在在哪一步**：畫布平鋪所有站點，沒有「起點在左、目前進行到哪」的視覺引導 | 全畫布 | 第一眼放棄 |
| 2 | **技術詞彙直接上卡**：run_id 短碼、artifact、`serial_region` 座標四元組（`regionSummary` 輸出 `0.62, 0.08, 0.3, 0.12`）、port 英文名 | `nodeCards.tsx` L218-224 | 看不懂=不敢按 |
| 3 | **數字沒有語意**：「rows 42」vs 應該是「42 列已判讀，3 列低信心 ⚠」；計數無對比、無高亮 | `NodeSummary` 2-metric 上限 | 看了等於沒看 |
| 4 | **狀態語言不統一**：tone 顏色、badge、邊框混用，dirty/低信心/錯誤分不出層級 | `statusBadges`/`toneColor` | 不知道哪裡要處理 |
| 5 | **可點與不可點分不出**：卡上按鈕、卡本體點選、port 沒有 affordance 差異 | `IsoNode` | 誤觸或不敢觸 |
| 6 | **guarded 只有鎖,沒有解釋**：🔒 有了,但「為什麼鎖、我能做什麼」沒就地說明 | export/apply 卡 | 以為壞掉 |
| 7 | **線沒有語意**：所有邊同色,PDF 流、表格流、參數流分不開;執行時看不出資料正在往哪流 | Canvas edges | 資料流讀不出來 |

### 1.2 節點尺寸/密度問題

- 全卡同寬 250px：純參數站（命名格式）被撐大、預覽站（ROI）被擠死——**要分尺寸等級**（§2.1）。
- 14 站全部平鋪 + 未來每頁子流程 → 初始視圖過密；**要分層 lane + 群組**（§4/§5）。
- 卡上 metric 上限 2 太摳，重要站（判讀結果）放不下「總數/成功/低信心/未判讀」四計數；**上限改依尺寸等級**。

### 1.3 資訊歸屬裁決（節點內 vs inspector/工程檢視）

| 放節點內 | 放 inspector（點選後） | 留工程檢視抽屜 |
|---|---|---|
| 站名+一句白話用途、狀態點、2-4 個關鍵計數、迷你預覽（L/XL 卡）、1-2 個主按鈕、dirty/guarded 標記 | 完整參數編輯、完整列表（rows/Pilot 全表）、大預覽+ROI 操作的進階模式、錯誤詳情與下一步、該站 run 證據摘要 | run log/graph JSON、流程樹、節點型錄、換軌守門、artifact 原文 |

原則：**節點卡回答「這站好了沒、結果大概如何」；inspector 回答「細節是什麼、我要怎麼改」；抽屜回答「工程師要查什麼」。**

## 2. ComfyUI-style 理想節點版面

### 2.1 統一卡片解剖（所有節點共用，先做這個再做個別站）

```text
┌─[圖示] 站名（中文）────────────── ●狀態─┐   尺寸等級：
│ 一句白話副標（灰小字）                    │   S=200px  純參數站
│ ─────────────────────────────         │   M=260px  資料站
│  body：計數列 / 摘要行 / 迷你預覽         │   L=340px  含小預覽
│  （依等級限制：S=2行 M=4行 L=預覽+3行）   │   XL=460px ROI 調校專用
│ ─────────────────────────────         │
│ [主按鈕] [次按鈕]                        │   port：圓點 + 中文 label
└─in ports（左緣）──────out ports（右緣）──┘   （handle id 維持英文契約）
```

五態視覺（全站一致，取代現在的混用）：

| 狀態 | 視覺 |
|---|---|
| 正常/完成 | 綠狀態點、實線邊 |
| 待更新 dirty | 琥珀虛線邊 + 右上「待重跑」膠囊；其下游同步淡琥珀 |
| 低信心/警告 | 卡內黃色計數膠囊（如「3 低信心」），邊框不變（警告屬內容不屬節點） |
| 錯誤 | 紅邊 + body 第一行=一句人話 + 按鈕變「重試」 |
| guarded/停用 | 灰底 + 🔒 +「需確認」膠囊；主按鈕文案=動作本名（「匯出…」「套用…」），點了走確認流程 |

### 2.2 各站規格（13 站；engine 對應欄說明它從哪取資料——**只是呈現映射，不改引擎**）

| 站 | 尺寸 | 卡內顯示 | in→out ports（id / 中文 label） | 按鈕 | 特別狀態 |
|---|---|---|---|---|---|
| 工作區 | M | 資料夾名、找到「合併 PDF ✓ / ISO 清單 ✓ / 拆頁資料夾 ✓✗」三勾 | →`work_folder`/工作區 | 選擇資料夾 | 未選=空狀態引導「從這裡開始」 |
| ISO 清單 | M | 檔名、大小、修改日 | `work_folder`→ / →`iso_list`/清單檔 | 更換檔案 | 找不到=琥珀「請選擇」 |
| 工作表 | S | sheet 名、列數 | `iso_list`→ / →`sheet`/工作表 | 切換 sheet（下拉） | 多 sheet 未確認=dirty |
| 欄位設定 | S | 流水號欄=C、圖號欄=F（欄字母+表頭名） | `sheet`→ / →`columns`/欄位 | 改欄位（下拉×2） | 猜測中=琥珀「自動猜測，請確認」 |
| 命名格式 | S | pattern 即時示例：`A123--PIPE-01.pdf`（用首列真資料渲染） | `columns`→ / →`pattern`/命名格式 | 編輯格式 | 非法 pattern=紅 |
| 合併 PDF | M | 檔名、頁數、檔案大小 | `work_folder`→ / →`combine_pdf`/合併檔 | 更換檔案 | — |
| 分割工具 | M | 狀態、拆頁資料夾短路徑、page count；side-effect chip「會寫入拆頁檔」 | `combine_pdf`→ / →`pages`/頁面、`page_folder` | 重新拆頁 | 已有拆頁=綠「沿用既有」 |
| 頁面 | M(群組頭) | 「48 頁 · 顯示 10」+ 低信心頁優先標示 | `pages`→ / →`page_sample`/取樣頁 | 展開更多 | §4 規格 |
| ROI 調校 | XL | §3 專節 | `page_sample`→ / →`serial_region`、`drawing_region`、`confidence_threshold`、`detect_serials`/判讀參數 | 只更新預覽/判讀此頁/重跑下游 | dirty 是常態狀態 |
| 判讀結果 | L | 四計數：總數/成功/**低信心**/未判讀 + 進度條（執行中）+ job 狀態白話 | `pages`,`iso_rows`,參數→ / →`rows`/判讀列 | 開始判讀、取消、重跑下游 | 執行中=藍邊+邊動畫 |
| 命名合成 | M | 成功合成 n/m、衝突 k、示例新名 1 行 | `rows`,`pattern`→ / →`named_rows`/命名列 | 查看清單（開 inspector） | 衝突>0=黃膠囊 |
| Pilot/結果表 | L | P01-P15 三色計數膠囊（✓n ⚠n ✗n）+ blocks_apply 紅字警示 | `named_rows`→ / →`pilot_results` | 重新檢查、看問題（開 inspector） | blocked>0=邊框不變、膠囊紅 |
| 匯出 CSV ∥ 套用更名 | M×2 | 匯出：上次路徑+列數;套用：ready n / blocked n + 上次套用 n 筆 | `named_rows`→ / →`csv_path`、`rename_result` | 匯出草稿 / 預覽更名+套用更名 | 永遠帶 🔒需確認;走既有受認可 action（exportIsoPlanCsv/applyIsoPlan+確認對話框），**不繞過** |

註：工作表/欄位設定/命名格式/命名合成是**呈現層拆分**（engine 端仍是 `load_table` inputs 與 rows 的 new_name 欄）；合成節點群只改 overlay inputs，dirty 傳播照 §8 既有模型。


## 3. ROI 調校節點詳細設計（XL 卡，460px）

```text
┌─🎯 ROI 調校 ─────────────────────●─┐
│ 框出流水號與圖號位置，調整判讀門檻        │
│ ┌─頁選擇：◀ 頁 3/48 ▶  [低信心頁▾]──┐ │
│ │                                  │ │
│ │      PDF 預覽（寬 428px,          │ │  ← 高度 = 428×1.414≈605px 太高
│ │      A4 直式縮放至高 ~420px,       │ │     → 取「fit 寬度、上限高 420」
│ │      超出捲動;含 RoiOverlay        │ │     橫式圖自然較矮
│ │      可拖兩個框:                   │ │
│ │      ▭ 流水號(藍) ▭ 圖號(紫)       │ │
│ └──────────────────────────────────┘ │
│ 裁切預覽：[流水號 crop] [圖號 crop]     │  ← 兩張小圖並排,高 64px
│ 門檻 ────────●──── 0.70   偵測 [on]   │  ← slider + toggle
│ 試判（本頁）：A123 (0.92) ✓            │  ← 有結果才顯示
│ [只更新預覽] [判讀此頁] [重跑下游 ⚠]    │
└─ in: page_sample ──── out: 判讀參數 ──┘
```

- **比例**：預覽區佔卡高 ~55%；裁切預覽列 ~12%；控制列 ~20%；按鈕列 ~13%。
- **兩個 ROI**：同一張預覽上兩個可拖框（藍=流水號、紫=圖號，沿用 `RoiOverlay` 的 activeRoi 切換）；點框=選中可拖拉端點；座標**不顯示四元組數字**（要看精確值去 inspector）。
- **三按鈕語意（必須在 tooltip 寫明）**：
  1. 「只更新預覽」＝純前端重新裁切 crop 預覽（`loadIsoPreview` 單頁、既有 debounce）——**零 OCR、零後端判讀**；
  2. 「判讀此頁」＝對目前頁跑一次單頁判讀（`loadIsoPreview` 帶 `detect_serial:true` 的既有單頁路徑）——便宜、即時回饋；
  3. 「重跑下游」＝以目前參數從判讀結果站起整批重跑（既有 `workflow_run_from` job）——昂貴，按鈕帶 ⚠ 與預估「48 頁」。
- **防自動 OCR**：拖框/拉 slider 只改 overlay state + debounce 後刷新**預覽**（按下「只更新預覽」等價行為可自動，因為它不含 OCR）；「判讀此頁」「重跑下游」永遠只由點擊觸發。靜態守門沿用：workbench 檔案 useEffect/onChange 禁 detect/run 字串。
- **單頁試判回寫**：結果存 overlay 的 `pageTrials[page]`（前端暫存,不寫 artifact）；ROI 卡顯示「試判：A123 (0.92)」；判讀結果站卡上顯示淡色提示「頁 3 有新試判,與上次批次結果不同 → 建議重跑下游」（比對 rows 中該頁 serial）；**batch rows artifact 仍是唯一真相**，試判只是調參回饋。

## 4. 大量頁面處理策略

1. **展開規則 v2**：預設展開 = `前 10 頁 ∪ 全部低信心頁 ∪ 全部未判讀頁`（上限 20；低信心優先佔位）——讓需要人工處理的頁自動浮到可見區，這是對「低信心頁是否自動浮上」的明確裁決：**要**。
2. **+more 節點**：頁面群組尾端一張 S 卡「+38 頁未顯示」，點擊每次再展開 20，捲動定位到新批；展開到 60 頁以上時頂部出現「收合至重點頁」回收按鈕。
3. **防畫布爆炸**：React Flow `onlyRenderVisibleElements` 開啟；頁縮圖一律 lazy（進 viewport 才 `loadIsoPreview`，離開即釋放 base64）；同時在記憶體保留上限 24 張縮圖（LRU）。
4. **群組呈現**：頁面子流程放在「頁面 lane」的 **frame**（React Flow group/subflow 視覺框，標題「頁面 48」）內垂直排列；frame 只是視覺容器，**不引入引擎 subgraph**。MVP 不做 lane 拖拉重排。

## 5. 畫布布局規格

- **初始 viewport**：`fitView({ padding: 0.15, maxZoom: 0.9 })` 聚焦主幹（工作區→判讀結果→Pilot）；左上角常駐「重置視圖」。
- **五欄分層（左→右）**：`來源`（工作區/合併PDF/ISO清單）→ `設定`（工作表/欄位/命名格式/分割工具/ROI調校）→ `處理`（頁面群組/判讀結果）→ `結果`（命名合成/Pilot）→ `輸出`（匯出/套用）。欄寬=最大卡寬+120px 走線間距。
- **雙分支分層**：ISO 分支（清單→工作表→欄位→命名格式）在上半，PDF 分支（合併PDF→分割→頁面→ROI）在下半，於「判讀結果」匯流——上資料、下影像，交叉線最少。
- **連線規則**：顏色按資料型別——PDF/頁面=藍、表格/列=綠、參數=灰、rows=橘、結果=紫；粗細 2px；執行中該段 `animated` + 加亮；dirty 下游=琥珀虛線；錯誤下游=灰化。箭頭沿用 ArrowClosed。
- **點選後 inspector**（右側 380px，§1.3 歸屬）：頂=站名+狀態+人話說明；中=該站完整內容（參數編輯/全表/大預覽）；底=「本站證據」摺疊（該 node 的 run 狀態、耗時、side-effect 紀錄一行版）。再點空白收合。

## 6. Codex 施工計畫（UI-1 ~ UI-5，每 phase 一 commit、可獨立驗收）

| Phase | 內容 | 主要檔案 | 驗收 |
|---|---|---|---|
| **UI-1 統一卡片系統** | 在現有 rich canvas 上整理卡片解剖+四尺寸等級+五態視覺+port 中文 label（handle id 不變）；技術值出卡（座標/run_id 進 inspector）；計數語意化（「3 低信心」黃膠囊） | `workbench/WorkflowGuideCanvas.tsx`、必要時 `workbench/NodeDetailPanel.tsx` | tsc/build/test:unit 綠；畫布上五態可同屏對照；卡上無英文 port 名、無座標四元組 |
| **UI-2 布局與線語意** | 五欄分層+雙分支上下排+初始 viewport/重置視圖；邊按型別著色、執行 animated、dirty 虛線 | `workbench/WorkflowGuideCanvas.tsx` | 開頁即見左側起點與 ISO/PDF 分支；工程檢視仍可用；新增 layout smoke 測試或 DOM smoke check |
| **UI-3 站點拆分與空狀態** | 精修現有 13 站呈現（工作表/欄位/命名格式/命名合成等為呈現層拆分）；未選工作區時仍能看到完整 P001 placeholder 管線；guarded 卡「需確認」說明 tooltip | `workbench/WorkflowGuideCanvas.tsx`、`workbench/NodeDetailPanel.tsx` | 13 站齊、dirty 傳播跨合成站正確；新手路徑：空畫布→選資料夾→各站亮起 |
| **UI-4 ROI XL 卡 + 單頁試判** | §3 全規格（雙框/裁切預覽/三按鈕/pageTrials 回寫提示），以目前 ROI rich node 為基礎補齊 | `workbench/WorkflowGuideCanvas.tsx`、`workbench/NodeDetailPanel.tsx` | 拖框 20 次零 OCR 請求；判讀此頁有單頁回饋；結果站出現「建議重跑」提示 |
| **UI-5 頁面群組 + 收尾** | §4 全規格（展開規則 v2/+more/frame/lazy 縮圖/LRU）；驗收 checklist 全跑；docs postscript；merge+tag `iso-workbench-uiux-v2` | `workbench/WorkflowGuideCanvas.tsx`、必要時新 `workbench/PageGroup.tsx` | 200 頁 fixture 開頁不卡（<2s 首繪）；低信心頁自動在可見區；full pytest+pollution+safety 契約 0 failed |

每 phase 收尾三件事不變：該 phase 驗證命令綠 → `git diff --stat` 不越界 → commit+push。後端唯一可動處：無（本期零後端；若 UI-4 發現單頁試判缺 API，停下回報——`loadIsoPreview` 既有能力應已足夠）。

## 7. 不要做（全期鐵則）

1. 不改 workflow engine、executor、schema、projection、parity/gate——一行都不改。
2. 不改 guarded policy 與 replay 封鎖；匯出/套用永遠走既有受認可 action + 既有確認對話框，**不得**因畫布互動變成快捷執行；前端永無 `workflow_allow`/`workflow_confirm`。
3. 不退回 wizard / 線性列表 / 表格報表主視覺。
4. 不在 slider/拖框/onChange/useEffect 觸發 OCR 或任何 run；「只更新預覽」不含偵測。
5. 不一次 render 全部 PDF 預覽；縮圖一律 lazy + LRU 上限。
6. 不做自訂接線編輯、增刪節點、佈局持久化、lane 拖拉（維持唯讀結構 + 可拖節點位置不保存）。
7. 不動一鍵/工作台/調校三分頁、E 期 engine flag/breaker、Pilot P01-P15、PyQt legacy、`.qwen/`。

---

## 給 Codex 的短版命令（直接貼）

```text
請讀 docs/iso_pdf_workbench_uiux_v2_spec_2026-06-11.md，它是節點工作台 UI/UX v2 的唯一規格。
Pre-flight：cd C:\Users\a0976\Documents\GitHub\桌面輔助系統 → git status 只允許 .qwen/ 未追蹤（永不 stage）→ git switch codex/tauri-react-spike && git pull --ff-only → 視需要 git switch -c codex/iso-workbench-uiux-v2。
照 UI-1→UI-5 施工，每 phase 一 commit + push + 驗收；請在現有 `workbench/WorkflowGuideCanvas.tsx` rich React Flow canvas 上精修，不要刪掉重做、不退回 wizard/list。
鐵則：只動 UI 層（優先 `workbench/WorkflowGuideCanvas.tsx` / `NodeDetailPanel.tsx`，必要時才動 `WorkflowCanvas.tsx` / `flowAdapter.ts` 工程檢視呈現端），engine/契約/policy 零修改；統一卡片解剖與五態視覺先行（UI-1）；port 顯示中文、handle id 維持英文；座標/run_id 等技術值離開卡面進 inspector；ROI 三按鈕語意分明，拖框拉桿零 OCR；頁面預設展開=前10頁∪低信心∪未判讀（上限20），縮圖 lazy+LRU；匯出/套用維持 🔒+既有確認；不做 wizard、不做接線編輯。
每 phase 跑：cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit；UI-5 加跑 python -m pytest tests\test_frontend_safety_contract.py tests\test_iso_workflow_pollution.py -q 與 full pytest。
卡關或規格未涵蓋 → 停下寫短報告，不要擴大。UI-5 完成 → merge --no-ff 回 codex/tauri-react-spike、tag iso-workbench-uiux-v2、停工回報（截圖全景一張 + 驗收勾選表）。
```
