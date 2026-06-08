# ISO PDF 拆頁命名 — 下一階段優化設計

> Date: 2026-06-08
> Scope: ISO PDF 拆頁命名功能的角色分層、UI 架構、Pilot List、Run Log、ROI 調校、狀態機、測試策略
> Principle: 保護一鍵穩定路線；工作台可複雜但層級清楚；調校資料可回復、可追蹤、可匯出

---

## 目錄

1. [角色與產品邊界](#1-角色與產品邊界)
2. [建議資訊架構（UI 佈局）](#2-建議資訊架構ui-佈局)
3. [Pilot List / Diagnostic Plan](#3-pilot-list--diagnostic-plan)
4. [Run Log / Error Log Schema](#4-run-log--error-log-schema)
5. [ROI 調校設計](#5-roi-調校設計)
6. [工作台狀態機](#6-工作台狀態機)
7. [一鍵失敗後的導流](#7-一鍵失敗後的導流)
8. [測試策略](#8-測試策略)
9. [建議模組 / 檔案結構](#9-建議模組--檔案結構)
10. [優先級](#10-優先級)

---

## 1. 角色與產品邊界

### 1.1 三層分離原則

| 層級 | 名稱 | 目標使用者 | 核心訴求 | 容錯空間 |
|------|------|-----------|---------|---------|
| L1 | **一鍵模式** | 長官、一般同事 | 選資料夾 → 按按鈕 → 拿到結果 | 零：失敗就導流，不暴露參數 |
| L2 | **工作台模式** | 工程師、資料校對者 | 看 plan table、修正問題列、重跑局部 | 中：可改 serial/line/pattern，不改 ROI |
| L3 | **調校模式** | 開發者、進階工程師 | 調 ROI、改 threshold、看 diagnostic、匯出 debug bundle | 高：所有參數可動，所有 log 可見 |

**為什麼是三層而非兩層？**
目前的 React `IsoPdfAutopilot` 已有 `autopilot` / `workbench` / `engineer` 三種 `isoView`，但 workbench 和 engineer 的邊界模糊。本次設計明確劃分：

- **L2 工作台**服務的是「一鍵跑完有問題列，我要修正後繼續」的人。操作對象是 **plan rows**，不是 OCR 參數。
- **L3 調校**服務的是「OCR 判讀不準，我要改善判讀品質」的人。操作對象是 **ROI region、threshold、vision engine**，不是 plan rows。

### 1.2 L1 一鍵模式 — 保留與排除

**必須保留的操作：**

| 操作 | 說明 |
|------|------|
| 選擇工作資料夾 | 唯一的輸入動作 |
| 「一鍵命名」按鈕 | 自動走完 discover → split → detect → plan → apply |
| 進度顯示 | 六階段 pipeline 視覺化 + event log |
| 結果摘要 | 成功數 / 問題數 / 阻擋數 |
| 「交給工程師」按鈕 | 失敗時匯出 debug bundle 並複製路徑 |

**絕對不該出現在 L1 的操作：**

| 排除項 | 原因 |
|--------|------|
| ROI 調整滑桿 | 一般使用者不知道什麼是 ROI |
| Confidence threshold | 一般使用者不知道什麼是信心值 |
| Pattern 編輯 | `{serial}--{line}.pdf` 預設值已覆蓋 95% 場景 |
| Sheet / Column 選擇 | 自動偵測已足夠；出問題由 L2/L3 處理 |
| Inline 表格編輯 | L1 不做人工修正 |
| 批次判讀按鈕 | 由一鍵流程內部觸發 |
| 匯出 CSV | L1 只在套用前自動匯出作為備份 |
| Developer mode toggle | 開發者直接去 L3 |

### 1.3 L2 工作台模式 — 服務角色

| 角色 | 典型場景 | 需要的功能 |
|------|---------|-----------|
| **資料校對者** | 一鍵跑完，有 3 列 serial 判讀錯誤 | 看問題列、inline 改 serial、重新產生該列命名、套用 |
| **工程師** | ISO List 欄位對應錯誤 | 改 sheet / serial_col / line_col、重新產生整個 plan |
| **問題排查者** | 某頁 PDF 檔名異常 | 搜尋特定列、看 vision_message、看 confidence |
| **專案管理者** | 需要存檔或交付 | 匯出 CSV、匯出 run log |

### 1.4 L3 調校模式 — 服務角色

| 角色 | 典型場景 | 需要的功能 |
|------|---------|-----------|
| **開發者** | 新專案的 PDF 格式不同，需要調 ROI | ROI overlay editor、多頁採樣、confidence heatmap |
| **進階工程師** | OCR 信心普遍偏低 | 調 threshold、切換 vision engine、看 two-stage 日誌 |
| **維護者** | 需要比較新舊 profile 效果 | Profile diff、profile version history |

---

## 2. 建議資訊架構（UI 佈局）

### 2.1 L1 一鍵模式

```
┌─────────────────────────────────────────────────────────────┐
│  頂部：工作資料夾選擇器                                       │
│  [📁 選擇資料夾]  D:\Projects\ISO-2026-001                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Pipeline 視覺化（6 階段橫向 stepper）                        │
│  [①來源] → [②拆頁] → [③判讀] → [④對ISO] → [⑤命名] → [⑥更名]│
│    ✓        ✓        ●         ○         ○         ○       │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │                                                 │        │
│  │          [ 🔧 一鍵命名目前資料夾 ]                 │        │
│  │                                                 │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  Event Log Terminal（最近 8 條事件，可展開）                   │
│  ▸ 12:34:05  [detect] page 23/42 serial=17 confidence=0.94  │
│  ▸ 12:34:03  [detect] page 22/42 serial=16 confidence=0.91  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  底部：結果摘要（完成後顯示）                                  │
│  ✅ 38 可更名  ⚠️ 3 需確認  🚫 1 阻擋                        │
│  [ 查看問題列 → L2 ]  [ 匯出問題包 → 交給工程師 ]             │
└─────────────────────────────────────────────────────────────┘
```

**關鍵設計決策：**
- Pipeline stepper 用 `steps` 陣列渲染（已有 `source.steps`），每步有 `state: ready|warn|blocked|running|empty`。
- Event log 從 `batchJob.events` 陣列取最近 8 條，用 `<details>` 可展開看全部。
- 失敗後底部出現兩個按鈕，明確分流：「查看問題列」進入 L2，「匯出問題包」產生 debug bundle。

### 2.2 L2 工作台模式

```
┌──────────┬──────────────────────────┬───────────────────┐
│  左欄     │  中欄                     │  右欄              │
│  320px    │  flex: 1                  │  380px             │
│  Sources  │  Plan Table              │  Visual Inspector  │
│  & Mapping│                          │                    │
├──────────┼──────────────────────────┼───────────────────┤
│          │                          │                    │
│ 📁 工作   │ [🔍搜尋] [☐只看問題列]     │  PDF 全頁預覽      │
│ 資料夾    │ [下一個問題 ↗]            │  ┌──────────────┐ │
│ D:\...\  │                          │  │  ┌─┐         │ │
│          │ ┌──────────────────────┐ │  │  │ROI│ serial │ │
│ 📄 ISO   │ │☑ │old│pg│serial│line│ │  │  └─┘         │ │
│ List     │ │☑ │p01│ 1│  17  │PA  │ │  │       ┌─┐    │ │
│ sheet: 1 │ │☑ │p02│ 2│  16  │PB  │ │  │       │ROI│   │ │
│ serial:0 │ │☐ │p03│ 3│  ??  │??  │ │  │       └─┘    │ │
│ line: 1  │ └──────────────────────┘ │  └──────────────┘ │
│          │                          │                    │
│ pattern: │  列狀態統計                │  Serial 裁切圖     │
│ {serial} │  ready: 38  warn: 3      │  ┌──────────────┐ │
│ --{line} │  blocked: 1  idle: 0     │  │  17          │ │
│ .pdf     │                          │  └──────────────┘ │
│          │                          │  Drawing 裁切圖    │
│ ✅ Checklist│ 動作列                  │  ┌──────────────┐ │
│ 來源 ✓   │ [重新產生] [批次判讀]      │  │  PIPE-A      │ │
│ ISO  ✓   │ [套用更名] [匯出 CSV]     │  └──────────────┘ │
│ 判讀 ✓   │ [匯出 Run Log]            │                    │
│ 命名 ⚠   │                          │  判讀值: 17        │
│          │                          │  信心: 0.94        │
│          │                          │  [採用判讀值]       │
│          │                          │  [確認此列]         │
├──────────┴──────────────────────────┴───────────────────┤
│  底部：Run Log 摘要（可展開為完整 log）                      │
│  ▸ Run #20260608-123405 | 42 pages | 38 ready | 3 warn   │
└─────────────────────────────────────────────────────────────┘
```

**關鍵設計決策：**

- **左欄 = 來源與對應**：資料夾、ISO List、sheet/column mapping、pattern。這些決定了 plan 的「輸入面」。改動任一項後，「重新產生」按鈕亮起。
- **中欄 = Plan Table**：這是 L2 的核心。使用者在這裡做 bulk review 和 inline correction。
  - 表格欄位：`☑` / `old name` / `page` / `serial` / `line_no` / `new_name` / `status` / `confidence`
  - `serial` 和 `line_no` 欄位可 inline 編輯（`<input>` 替換 `<span>` on click）
  - `status` 欄位用色碼 chip：`ready`=綠、`warn`=黃、`blocked`=紅、`idle`=灰
  - `confidence` 欄位用小字 chip：>=0.90 綠、>=0.70 黃、<0.70 紅
- **右欄 = Visual Inspector**：預覽 + ROI 裁切圖 + 判讀值。這是「看證據」的地方。
  - ROI 框疊加在全頁預覽上（`RoiBox` absolute 定位），但**不可拖曳**（拖曳是 L3 的功能）
  - Serial/Drawing 裁切圖顯示 base64 PNG
  - 「採用判讀值」和「確認此列」按鈕，行為與現有 PyQt6 一致

**L2 Tabs 設計：**

中欄頂部有兩個 tab：

| Tab | 內容 | 何時使用 |
|-----|------|---------|
| **命名草稿** | Plan Table + 統計 + 動作按鈕 | 預設 tab，review 和修正 |
| **Run History** | 本次 session 的 run log 列表，可點開看詳情 | 需要回溯之前的嘗試 |

### 2.3 L3 調校模式

```
┌──────────┬──────────────────────────┬───────────────────┐
│  左欄     │  中欄                     │  右欄              │
│  320px    │  flex: 1                  │  380px             │
│  Sources  │  ROI Editor / Diagnostic │  Visual Inspector  │
│  & Profile│                          │  (同 L2)           │
├──────────┼──────────────────────────┼───────────────────┤
│          │                          │                    │
│ 📁 工作   │  [ROI Editor] [Diag]     │  PDF 全頁預覽      │
│ 資料夾    │                          │  + ROI overlay     │
│          │  ── ROI Editor ──        │  (可互動)           │
│ 📄 ISO   │  Serial Region:          │                    │
│ List     │  ┌──────────────────────┐│  Serial 裁切圖     │
│          │  │  多頁採樣預覽         ││  Drawing 裁切圖    │
│ Profile: │  │  page 1 [0.94] ✓     ││                    │
│  v2.1    │  │  page 5 [0.87] ✓     ││  Confidence Map   │
│ [載入]   │  │  page 9 [0.62] ⚠     ││  ┌──────────────┐ │
│ [儲存]   │  │  page 13 [0.41] 🚫   ││  │  heatmap     │ │
│ [重設]   │  └──────────────────────┘│  └──────────────┘ │
│ [匯出]   │                          │                    │
│          │  L: 0.62  T: 0.00       │  Vision Engine     │
│ Quality  │  W: 0.38  H: 0.24       │  ┌──────────────┐ │
│ Gates    │                          │  │ CV: 17 (0.91)│ │
│ [全部]   │  [自動校準]              │  │ OCR: 17 (0.94)│ │
│          │  [重設為預設]             │  │ Merge: 17    │ │
│ Threshold│  [用此頁 ROI 套用到全部]   │  │ (0.94)       │ │
│ ━━━●━━━  │                          │  └──────────────┘ │
│ 0.70     │  ── Diagnostic Tab ──    │                    │
│          │  (見 2.4 節)              │  [🔧 套用 ROI 並  │
│ Engines  │                          │   重跑 batch]      │
│ ☑ CV     │                          │                    │
│ ☑ OCR    │                          │                    │
└──────────┴──────────────────────────┴───────────────────┘
```

**L3 獨有功能：**

| 功能 | 說明 | Developer Mode Only |
|------|------|-------------------|
| ROI 拖曳編輯器 | 可在 PDF 預覽上直接拖曳 ROI 框 | 否 |
| 多頁採樣 | 顯示 4~8 頁的 serial region 裁切 + confidence | 否 |
| Confidence heatmap | 將 confidence 值疊加在 PDF 預覽上 | 是 |
| Vision engine 切換 | 可單獨關閉 CV 或 OCR，觀察各引擎結果 | 是 |
| Profile 版本管理 | 儲存/載入/匯入/匯出 profile | 否 |
| Raw diagnostic JSON | 顯示完整的 vision result JSON | 是 |
| Replay payload | 顯示可複製的 replay command | 是 |

**L3 中欄 Tabs：**

| Tab | 內容 |
|-----|------|
| **ROI Editor** | 多頁採樣 + 四邊滑桿 + 自動校準 + 重設 |
| **Diagnostic** | Raw vision JSON、two-stage 日誌、correction 歷程 |
| **Job Protocol** | Batch detect job 狀態、cancel、log tail |

### 2.4 Developer Mode 控制

沿用現有 `AppStateStore` 的 `developer_mode` flag：

- L1 一鍵模式：**永遠不顯示** developer-only 功能
- L2 工作台模式：developer mode 開啟時，在 Run History tab 顯示 raw JSON
- L3 調校模式：developer mode 開啟時，顯示 Confidence heatmap、Vision engine 切換、Raw diagnostic JSON、Replay payload

**如何避免一般使用者被工程資訊嚇到：**
- L1 完全沒有技術名詞（不顯示 ROI、confidence、threshold、serial vision）
- L2 只在 hover 時用 tooltip 解釋技術欄位（例如 confidence 欄位 hover 顯示「判讀信心：越高越好，低於 0.70 會標為需確認」）
- L3 的工程資訊預設收合在 `<details>` 或 tab 中，需要主動點開

---

## 3. Pilot List / Diagnostic Plan

### 3.1 Pilot List 總覽

Pilot List 是工作台 L2/L3 中「命名草稿產生過程」的逐步驟驗證清單。每個 pilot item 代表一個可驗證的檢查點。

> 與現有 `validator.py` 的 7 項 checklist 的關係：
> - Checklist 是 **事前** 驗證（還沒開始跑之前的條件檢查）
> - Pilot List 是 **事中 + 事後** 驗證（跑的過程中的逐步結果 + 最終診斷）

### 3.2 Pilot Item 規格

每個 pilot item 包含以下欄位：

```typescript
interface PilotItem {
  id: string;                    // 唯一識別碼，例如 "P01_input_discovery"
  name: string;                  // 顯示名稱
  purpose: string;               // 目的說明
  stage: "pre" | "run" | "post"; // 事前/事中/事後
  inputs: string[];              // 需要的輸入資料
  successCondition: string;      // 成功條件（程式可判定）
  warnCondition: string;         // 警告條件
  blockedCondition: string;      // 阻擋條件
  userText: string;              // 給一般使用者的文字
  engineerText: string;          // 給工程師的詳細診斷
  autoFix?: string;              // 可自動修復的動作描述
  manualAction?: string;         // 需要人工調整的動作描述
}
```

### 3.3 完整 Pilot List（17 項）

#### P01 — Input Discovery（來源探索）

| 欄位 | 值 |
|------|---|
| **id** | `P01_input_discovery` |
| **name** | 來源探索 |
| **purpose** | 從工作資料夾自動偵測 combine PDF、page folder、ISO list |
| **stage** | `pre` |
| **inputs** | `work_folder` 路徑 |
| **success** | 找到 combine PDF 或 page folder，且找到至少一個 ISO list 候選 |
| **warn** | 找到 PDF 但 ISO list 有多個候選需選擇；或找到 page folder 但無 combine PDF |
| **blocked** | 資料夾不存在或為空；找不到任何 PDF |
| **userText** | 「正在掃描資料夾中的 PDF 和 ISO 清單...」 |
| **engineerText** | `_source_discovery()` 搜尋 `{work_folder}/*.pdf` 和 `{work_folder}/*.xlsx`，combine PDF 偏好含 "combine"/"合併" 關鍵字，ISO list 依檔名關鍵字評分（iso=40, 圖號=35, 清單=25）。候選路徑和分數記錄在 `source.iso_candidates` |
| **autoFix** | 無 |
| **manualAction** | 手動選擇 combine PDF 或 ISO list 檔案 |

#### P02 — PDF Source Check（PDF 來源驗證）

| 欄位 | 值 |
|------|---|
| **id** | `P02_pdf_source` |
| **name** | PDF 來源驗證 |
| **purpose** | 確認 PDF 來源類型和頁數 |
| **stage** | `pre` |
| **inputs** | `combine_pdf` 或 `page_folder` 路徑 |
| **success** | `source.kind` 為 `combine_pdf` / `existing_pages` / `page_folder` / `work_folder_pages`，且 `pdf_count > 0` |
| **warn** | PDF 頁數與 ISO list 列數不一致 |
| **blocked** | PDF 檔案無法開啟（損壞或加密）；page folder 無任何 `.pdf` 檔 |
| **userText** | 「找到 {n} 頁 PDF」 |
| **engineerText** | `source.kind={kind}`，`pdf_count={n}`。combine PDF 用 `pypdf.PdfReader` 開啟，page folder 用 `sorted(folder.glob("*.pdf"))` |
| **autoFix** | 無 |
| **manualAction** | 確認 PDF 路徑正確；若 PDF 加密需先解密 |

#### P03 — Page Split Check（拆頁驗證）

| 欄位 | 值 |
|------|---|
| **id** | `P03_page_split` |
| **name** | 拆頁驗證 |
| **purpose** | 確認合併 PDF 已正確拆成單頁 |
| **stage** | `run` |
| **inputs** | `combine_pdf` 路徑、`page_folder` 路徑 |
| **success** | `page_folder` 存在且包含與 `pdf_count` 相同數量的單頁 PDF |
| **warn** | `page_folder` 已有舊拆頁結果（可能過期） |
| **blocked** | 無法建立 `page_folder`（權限不足）；拆頁過程 PDF 讀取失敗 |
| **userText** | 「已拆成 {n} 頁單頁 PDF」 |
| **engineerText** | `split_pdf_to_pages()` 輸出到 `{stem}_pages/`，格式 `{stem}_p{index:03d}.pdf`。若資料夾已存在，直接使用不重拆 |
| **autoFix** | 自動拆頁（`split_pdf` action） |
| **manualAction** | 若舊拆頁結果過期，手動刪除 `_pages` 資料夾後重跑 |

#### P04 — ISO List Parse Check（ISO 清單解析）

| 欄位 | 值 |
|------|---|
| **id** | `P04_iso_list_parse` |
| **name** | ISO 清單解析 |
| **purpose** | 正確讀取 ISO List 的 sheet、header、records |
| **stage** | `pre` |
| **inputs** | `iso_list` 路徑 |
| **success** | `source.record_count > 0`，`headers` 非空，`serial_col` 和 `line_col` 已判定 |
| **warn** | 使用 fallback 欄位（line_no 取代 file_basename）；encoding 非 UTF-8 |
| **blocked** | 檔案不存在；所有 sheet 都找不到 serial/line 欄位；檔案格式不支援 |
| **userText** | 「ISO 清單：{n} 筆記錄，欄位 [{serial_header}, {line_header}]」 |
| **engineerText** | `read_iso_table()` 在前 20 行搜尋 header row，`guess_iso_columns()` 比對 `SERIAL_HEADERS` / `DRAWING_NAME_HEADERS` / `LINE_HEADERS`。編碼嘗試順序：utf-8-sig → cp950 → big5 |
| **autoFix** | 嘗試所有 encoding；自動選擇最佳 sheet |
| **manualAction** | 在 L2 左欄手動選擇 sheet / serial_col / line_col |

#### P05 — Sheet / Column Mapping Check（欄位對應驗證）

| 欄位 | 值 |
|------|---|
| **id** | `P05_column_mapping` |
| **name** | 欄位對應驗證 |
| **purpose** | 確認 serial 欄和 line 欄的內容合理 |
| **stage** | `pre` |
| **inputs** | `IsoTable` records |
| **success** | serial 欄全為數字或可排序值；line 欄非空比例 > 80% |
| **warn** | serial 欄有空白列；line 欄有超過 20% 空白 |
| **blocked** | serial 欄全空；line 欄全空；serial_col == line_col |
| **userText** | 「流水號欄 [{header}]、圖號欄 [{header}]」 |
| **engineerText** | `IsoRecord(serial={...}, line_no={...})` 前 5 筆 sample 記錄。serial 欄非空比例 {x}%，line 欄非空比例 {y}% |
| **autoFix** | 無 |
| **manualAction** | 在 L2 左欄切換 serial_col / line_col |

#### P06 — Serial Number Detection（流水號判讀）

| 欄位 | 值 |
|------|---|
| **id** | `P06_serial_detection` |
| **name** | 流水號判讀 |
| **purpose** | 用 OpenCV + RapidOCR 雙引擎從 PDF 頁面偵測流水號 |
| **stage** | `run` |
| **inputs** | 單頁 PDF、`serial_region`、`confidence_threshold` |
| **success** | 偵測到流水號且 confidence >= threshold |
| **warn** | 偵測到但 confidence < threshold；兩引擎結果不一致 |
| **blocked** | 兩引擎都無法偵測；cv2/rapidocr 未安裝 |
| **userText** | 「判讀流水號 {serial}（信心 {confidence}）」 |
| **engineerText** | `detect_serial_from_pdf()` 雙引擎融合：CV template match (960 templates) + RapidOCR。Merge 策略：相同取 max conf、包含關係取內側、高信心獨立取。Two-stage 先 `calibrate_serial_region_from_bgr()` 找「流水號」文字定位 ROI |
| **autoFix** | Two-stage 自動校準 ROI；ISO list lookup correction（trim 左右各 ≤2 字元） |
| **manualAction** | 在 L2 表格 inline 改 serial；在 L3 調 ROI |

#### P07 — Drawing Number Detection（圖號偵測）

| 欄位 | 值 |
|------|---|
| **id** | `P07_drawing_detection` |
| **name** | 圖號偵測 |
| **purpose** | 從 ISO List 取得圖號/檔名對應 |
| **stage** | `run` |
| **inputs** | `IsoRecord` list、detected serial |
| **success** | serial 在 ISO List 中找到對應 line_no |
| **warn** | line_no 為空（將使用 fallback 命名） |
| **blocked** | serial 不在 ISO List 中且無 fallback |
| **userText** | 「圖號 {line_no}」 |
| **engineerText** | `serial → line_no` lookup 使用 `correct_result_with_iso_lookup()` 校正。校正嘗試 trim left/right ≤2 chars，評分 `len*10 - trim_count`。`_drawing_name_text()` 去除 `.pdf` 後綴並解析 `\d+--(.+)` 格式 |
| **autoFix** | ISO list correction 自動 trim |
| **manualAction** | 在 L2 表格 inline 改 line_no |

#### P08 — ROI Confidence（ROI 信心評估）

| 欄位 | 值 |
|------|---|
| **id** | `P08_roi_confidence` |
| **name** | ROI 信心評估 |
| **purpose** | 評估目前 ROI 設定在整個 batch 中的判讀品質 |
| **stage** | `post` |
| **inputs** | batch detect 完成後的 confidence 分布 |
| **success** | 平均 confidence >= 0.85 且 < threshold 的比例 < 10% |
| **warn** | 平均 confidence < 0.85 或 < threshold 比例 10~30% |
| **blocked** | < threshold 比例 > 50%（ROI 嚴重偏移） |
| **userText** | 「判讀品質：{avg_confidence} 平均信心，{n} 頁需確認」 |
| **engineerText** | Confidence 分布：>=0.90={a}, 0.70~0.90={b}, <0.70={c}。Two-stage 校準命中率 {calibrated}/{total}。快速 ROI 命中率 {fast}/{total} |
| **autoFix** | 建議重新自動校準 ROI |
| **manualAction** | 在 L3 調校 ROI region |

#### P09 — Duplicate Detection（重複偵測）

| 欄位 | 值 |
|------|---|
| **id** | `P09_duplicate` |
| **name** | 重複偵測 |
| **purpose** | 偵測命名結果中是否有重複的目標檔名 |
| **stage** | `post` |
| **inputs** | 所有 plan rows 的 `new_name` |
| **success** | 無重複的 `new_name` |
| **warn** | 有重複但其中一列可取消 selected |
| **blocked** | 有重複且兩列都 selected（更名會衝突） |
| **userText** | 「{n} 組重複檔名需處理」 |
| **engineerText** | `normalizeIsoRows()` 前端二次驗證：統計 `new_name` 出現次數，重複的標為 `blocked`，note = "目標檔名重複: {other_rows}" |
| **autoFix** | 保留 confidence 較高的一列，取消其他 |
| **manualAction** | 在 L2 表格取消其中一列或改 serial |

#### P10 — Missing Serial Detection（缺漏偵測）

| 欄位 | 值 |
|------|---|
| **id** | `P10_missing_serial` |
| **name** | 缺漏偵測 |
| **purpose** | 偵測 ISO List 中有但 PDF 中沒有的流水號，以及反過來 |
| **stage** | `post` |
| **inputs** | ISO List serials、detected serials |
| **success** | ISO List 和 PDF 頁數完全對應 |
| **warn** | ISO List 有 > PDF 頁數（可能有些圖未包含在 PDF 中） |
| **blocked** | PDF 頁數 > ISO List 記錄數（多出的頁面無對應圖號） |
| **userText** | 「ISO 清單 {iso_count} 筆 vs PDF {pdf_count} 頁」 |
| **engineerText** | ISO serials set minus detected serials set = {missing_in_pdf}。Detected serials minus ISO serials = {extra_in_pdf} |
| **autoFix** | 無 |
| **manualAction** | 確認 PDF 是否完整；確認 ISO List 是否正確版本 |

#### P11 — Naming Pattern Validation（命名格式驗證）

| 欄位 | 值 |
|------|---|
| **id** | `P11_pattern_validation` |
| **name** | 命名格式驗證 |
| **purpose** | 驗證 pattern 產生的檔名符合 Windows 檔案命名規則 |
| **stage** | `post` |
| **inputs** | `pattern`、所有 plan rows 的 `new_name` |
| **success** | 所有 `new_name` 無 Windows 非法字元、非保留名稱、無結尾空白/句點 |
| **warn** | 有 `new_name` 包含非 ASCII 字元 |
| **blocked** | 有 `new_name` 含 `\ / : * ? " < > |` 或為保留名稱（CON, PRN 等） |
| **userText** | 「命名格式檢查通過」或「{n} 個檔名無效」 |
| **engineerText** | `normalizeIsoRows()` Windows 規則檢查：`/[\\/:*?"<>|]/` 匹配、trailing space/period、reserved names。Pattern 模板 `{serial}--{line}.pdf` 展開後驗證 |
| **autoFix** | 自動替換非法字元為 `_` |
| **manualAction** | 修改 pattern 或個別 new_name |

#### P12 — Rename Draft Generation（命名草稿產生）

| 欄位 | 值 |
|------|---|
| **id** | `P12_draft_generation` |
| **name** | 命名草稿產生 |
| **purpose** | 整合所有資訊產生完整的 rename plan |
| **stage** | `post` |
| **inputs** | 所有 plan rows、summary、issues |
| **success** | `summary.ready > 0` 且 `summary.blocked == 0` |
| **warn** | `summary.warn > 0` |
| **blocked** | `summary.ready == 0` 或 `summary.blocked > summary.ready` |
| **userText** | 「命名草稿：{ready} 可更名，{warn} 需確認，{blocked} 阻擋」 |
| **engineerText** | `IsoWorkflowPlan.summary = {total, ready, warn, blocked, selected}`。Steps: {steps JSON}。Issues: {issues JSON} |
| **autoFix** | 無 |
| **manualAction** | 進入 L2 工作台修正問題列 |

#### P13 — Blocked Rows Explanation（阻擋列說明）

| 欄位 | 值 |
|------|---|
| **id** | `P13_blocked_explanation` |
| **name** | 阻擋列說明 |
| **purpose** | 為每個 blocked 列提供明確的原因和修正路徑 |
| **stage** | `post` |
| **inputs** | `status == "blocked"` 的 plan rows |
| **success** | 無 blocked 列 |
| **warn** | blocked 列有明確的 autoFix 路徑 |
| **blocked** | blocked 列原因不明（fallback blocked） |
| **userText** | 「{n} 列無法更名：{原因摘要}」 |
| **engineerText** | Blocked 原因分類：`no_new_name`（無圖號對應）、`invalid_name`（非法字元）、`no_line`（缺圖號）、`duplicate_target`（檔名重複）、`target_exists`（目標已存在）。每列 `note` 欄位有詳細原因 |
| **autoFix** | `target_exists` → 可選覆蓋；`duplicate_target` → 自動取消低信心列 |
| **manualAction** | 在 L2 修正 serial/line_no/new_name |

#### P14 — Manual Correction Path（人工修正路徑）

| 欄位 | 值 |
|------|---|
| **id** | `P14_manual_correction` |
| **name** | 人工修正路徑 |
| **purpose** | 提供問題列的修正工具和流程 |
| **stage** | `post` |
| **inputs** | warn/blocked plan rows |
| **success** | 所有原本 warn/blocked 的列已修正為 ready |
| **warn** | 部分列已修正但仍有剩餘 warn |
| **blocked** | 有列無法修正（需外部輸入） |
| **userText** | 「請修正以下問題列後再套用」 |
| **engineerText** | 修正工具：inline 編輯 serial/line_no、採用 vision 判讀值、確認此列（清除 review issue）、搜尋跳轉。`_apply_detected_serial_to_row()` 填入 OCR 值，`_regenerate_names()` 重算 new_name |
| **autoFix** | 「採用判讀值」按鈕自動填入 vision 結果 |
| **manualAction** | 手動輸入正確的 serial / line_no / new_name |

#### P15 — Apply / Dry-Run / Rollback Path（套用 / 試跑 / 回復）

| 欄位 | 值 |
|------|---|
| **id** | `P15_apply_rollback` |
| **name** | 套用 / 試跑 / 回復 |
| **purpose** | 安全地執行更名，支援 dry-run 和 rollback |
| **stage** | `post` |
| **inputs** | selected plan rows |
| **success** | `apply` 完成且 `renamed_count == summary.selected` |
| **warn** | 部分列更名成功、部分失敗 |
| **blocked** | 檔案被鎖定（Windows file lock）；權限不足 |
| **userText** | 「已更名 {n} 個 PDF」 |
| **engineerText** | `_apply_operations()` 呼叫 `Path.rename()`。套用前先 `export_plan_csv()` 備份。Rollback：從 CSV 讀取 original → new 對應，反向 rename。Windows file lock 偵測用 `RestartManager` API (`file_locks.py`) |
| **autoFix** | 無 |
| **manualAction** | 關閉佔用檔案的程式後重試；或從 CSV 手動反向更名 |

#### P16 — Export Log / Report Path（匯出紀錄）

| 欄位 | 值 |
|------|---|
| **id** | `P16_export_log` |
| **name** | 匯出紀錄 |
| **purpose** | 將本次執行的完整紀錄匯出為可交付的檔案 |
| **stage** | `post` |
| **inputs** | run log、plan rows、profile |
| **success** | 成功匯出 CSV + Run Log JSON + debug bundle（若失敗） |
| **warn** | 部分匯出路徑不可寫 |
| **blocked** | 無 |
| **userText** | 「紀錄已匯出到 {path}」 |
| **engineerText** | 匯出項目：`rename_plan.csv`（已有 `export_plan_csv`）、`run_log.json`（見第 4 節 schema）、`debug_bundle.zip`（含 profile、run log、sample pages、vision results） |
| **autoFix** | 無 |
| **manualAction** | 指定匯出路徑 |

#### P17 — Profile Persistence（Profile 持久化）

| 欄位 | 值 |
|------|---|
| **id** | `P17_profile_persistence` |
| **name** | Profile 持久化 |
| **purpose** | 確保 ROI 和設定正確存檔，下次開啟可還原 |
| **stage** | `pre` |
| **inputs** | `profile_folder` 路徑 |
| **success** | `load_profile` 成功還原所有設定 |
| **warn** | Profile 存在但部分欄位使用預設值 |
| **blocked** | Profile 檔案損壞（JSON parse error） |
| **userText** | 「已載入此資料夾的設定」 |
| **engineerText** | `AppStateStore.iso_naming_profile(folder)` 從 `state.json` 讀取。`IsoNamingProfile.to_payload()` 含 `serial_region`、`drawing_region`、`confidence_threshold`、`pattern`、`iso_list_path`、`sheet_name`、`serial_col`、`line_col` |
| **autoFix** | Profile 損壞時自動 fallback 到預設值 |
| **manualAction** | 在 L3 重新調整並儲存 profile |

### 3.4 Pilot List UI 渲染

Pilot List 在 L2 工作台模式的 **Run History** tab 中渲染：

```
Run #20260608-123405
  ✓ P01 來源探索          找到 combine.pdf + iso_list.xlsx
  ✓ P02 PDF 來源驗證      42 頁
  ✓ P03 拆頁驗證          已拆成 42 頁
  ✓ P04 ISO 清單解析      42 筆記錄 [流水號, 圖號]
  ✓ P05 欄位對應驗證      serial=0, line=1
  ● P06 流水號判讀        38 成功, 3 低信心, 1 失敗
  ✓ P07 圖號偵測          41 對應成功
  ⚠ P08 ROI 信心評估      平均 0.82, 4 頁需確認
  ✓ P09 重複偵測          無重複
  ⚠ P10 缺漏偵測          ISO 42 筆 vs PDF 42 頁 (1 筆 serial 不在 PDF)
  ✓ P11 命名格式驗證      通過
  ⚠ P12 命名草稿產生      38 ready, 3 warn, 1 blocked
  🚫 P13 阻擋列說明       1 列: p37 無圖號對應
  → P14 人工修正路徑      3 列待修正
  ○ P15 套用/試跑/回復    等待修正完成
  ○ P16 匯出紀錄          等待套用
  ✓ P17 Profile 持久化    已載入
```

每項可展開看 `engineerText`（僅 L3 / developer mode 顯示完整 diagnostic）。

---

## 4. Run Log / Error Log Schema

### 4.1 Run Log Schema

```json
{
  "schema_version": 2,
  "run_id": "20260608-123405-a1b2c3",
  "timestamp": "2026-06-08T12:34:05.123+08:00",
  "duration_ms": 45230,

  "input": {
    "work_folder": "D:\\Projects\\ISO-2026-001",
    "combine_pdf": "D:\\Projects\\ISO-2026-001\\combine.pdf",
    "page_folder": "D:\\Projects\\ISO-2026-001\\combine_pages",
    "iso_list": "D:\\Projects\\ISO-2026-001\\iso_list.xlsx",
    "profile_folder": "D:\\Projects\\ISO-2026-001"
  },

  "profile": {
    "serial_region": { "left": 0.62, "top": 0.0, "width": 0.38, "height": 0.24 },
    "drawing_region": { "left": 0.50, "top": 0.66, "width": 0.50, "height": 0.34 },
    "confidence_threshold": 0.70,
    "pattern": "{serial}--{line}.pdf",
    "sheet_name": "Sheet1",
    "serial_col": 0,
    "line_col": 1,
    "detect_serials": true
  },

  "pipeline": {
    "stages": [
      { "id": "discover", "status": "ok", "started_at": "...", "finished_at": "...", "duration_ms": 120 },
      { "id": "split", "status": "ok", "duration_ms": 3400, "detail": "42 pages" },
      { "id": "iso_parse", "status": "ok", "duration_ms": 890, "detail": "42 records, encoding=utf-8-sig" },
      { "id": "batch_detect", "status": "ok", "duration_ms": 38000, "detail": "38 ok, 3 low_conf, 1 fail" },
      { "id": "plan", "status": "ok", "duration_ms": 450, "detail": "38 ready, 3 warn, 1 blocked" },
      { "id": "apply", "status": "skipped", "detail": "blocked rows pending review" }
    ]
  },

  "iso_table": {
    "path": "D:\\Projects\\ISO-2026-001\\iso_list.xlsx",
    "sheet_name": "Sheet1",
    "header_row_index": 2,
    "headers": ["流水號", "圖號", "管線號", "備註"],
    "serial_col": 0,
    "line_col": 1,
    "record_count": 42,
    "encoding": null,
    "sample_records": [
      { "serial": "1", "line_no": "PIPE-A" },
      { "serial": "2", "line_no": "PIPE-B" },
      { "serial": "3", "line_no": "PIPE-C" }
    ]
  },

  "summary": {
    "total": 42,
    "ready": 38,
    "warn": 3,
    "blocked": 1,
    "idle": 0,
    "selected": 38
  },

  "pilot_results": [
    { "id": "P01_input_discovery", "state": "success", "detail": "..." },
    { "id": "P06_serial_detection", "state": "warn", "detail": "3 pages below threshold" }
  ],

  "failed_stage": null,

  "exception": null,

  "user_summary": "已產生命名草稿：38 可更名、3 需確認、1 阻擋。請在工作台修正後套用。",

  "developer_diagnostic": {
    "source_kind": "combine_pdf",
    "pdf_count": 42,
    "vision_engine_available": { "opencv": true, "rapidocr": true },
    "two_stage_calibration_hits": 35,
    "fast_roi_hits": 30,
    "confidence_distribution": {
      "high_gte_0.90": 32,
      "mid_0.70_to_0.90": 6,
      "low_lt_0.70": 3,
      "none": 1
    },
    "correction_applied_count": 5,
    "correction_ambiguous_count": 0,
    "merge_strategy_counts": {
      "agree": 28,
      "ocr_contains_cv": 4,
      "cv_contains_ocr": 2,
      "ocr_high_alone": 3,
      "cv_fallback": 5
    }
  },

  "suggested_next_actions": [
    {
      "action": "review_warn_rows",
      "label": "在工作台修正 3 列需確認項目",
      "target_mode": "workbench"
    },
    {
      "action": "tune_roi",
      "label": "在調校模式調整 ROI（平均信心偏低）",
      "target_mode": "engineer",
      "condition": "avg_confidence < 0.85"
    }
  ],

  "replay": {
    "command": "python -m launcher.app.tauri_iso_workflow",
    "payload": {
      "action": "plan",
      "work_folder": "D:\\Projects\\ISO-2026-001",
      "profile_folder": "D:\\Projects\\ISO-2026-001",
      "detect_serials": true
    }
  },

  "rows": [
    {
      "id": "row-1",
      "page": 1,
      "source_name": "combine_p001.pdf",
      "serial": "1",
      "line_no": "PIPE-A",
      "new_name": "1--PIPE-A.pdf",
      "status": "ready",
      "selected": true,
      "confidence": 0.94,
      "vision_message": "OCR+OpenCV：17 (0.94)",
      "note": ""
    }
  ],

  "apply_result": null
}
```

### 4.2 Error Extension（失敗時追加）

當 `failed_stage` 不為 null 時，run log 追加以下欄位：

```json
{
  "failed_stage": "batch_detect",

  "exception": {
    "type": "PermissionError",
    "message": "[WinError 5] Access is denied: 'D:\\...\\combine_p015.pdf'",
    "traceback": "Traceback (most recent call last):\n  File ...",
    "file": "D:\\...\\combine_p015.pdf",
    "errno": 5
  },

  "user_summary": "處理第 15 頁時發生錯誤：檔案被其他程式佔用。請關閉佔用程式後重試。",

  "suggested_next_actions": [
    {
      "action": "close_locking_app",
      "label": "關閉佔用檔案的程式後重試",
      "detail": "使用檔案佔用檢查器找出佔用程式"
    },
    {
      "action": "export_debug_bundle",
      "label": "匯出問題包交給工程師"
    }
  ],

  "partial_result": {
    "pages_processed": 14,
    "pages_remaining": 28,
    "last_successful_row": { "id": "row-14", "page": 14, "serial": "14" }
  }
}
```

### 4.3 Debug Bundle 結構

當使用者點「匯出問題包」時，產生一個 `.zip` 檔案：

```
debug_bundle_{run_id}.zip
├── run_log.json              # 完整 run log
├── rename_plan.csv           # 命名草稿 CSV
├── profile.json              # IsoNamingProfile payload
├── iso_list_sample.csv       # ISO List 前 50 列（脫敏）
├── sample_pages/             # 問題頁的 PDF 原始檔（最多 5 頁）
│   ├── combine_p003.pdf
│   ├── combine_p015.pdf
│   └── combine_p037.pdf
├── vision_results.json       # 問題頁的完整 vision result
└── environment.json          # Python version, cv2 version, rapidocr version, OS
```

### 4.4 Run Log 存檔策略

| 項目 | 規則 |
|------|------|
| 存檔位置 | `{runtime_root}/runs/iso/{run_id}.json` |
| 自動保留 | 最近 50 筆 |
| 歸檔 | 超過 50 筆時，最舊的移到 `{runtime_root}/runs/iso/_archive/` |
| 刪除 | `_archive/` 中超過 30 天的自動刪除 |
| 觸發時機 | `register_current_app_process()` 啟動時清理 |

### 4.5 Run Log 寫入時機

| 時機 | 行為 |
|------|------|
| batch detect 開始 | 寫入初始 run log（`pipeline.stages` 前 3 項已填） |
| batch detect 每 10 頁 | 增量更新 `rows` 和 `summary` |
| batch detect 完成 | 寫入完整 run log |
| batch detect 失敗 | 寫入含 `exception` 的 run log |
| apply 完成 | 追加 `apply_result` |
| apply 失敗 | 追加 `apply_result` + `exception` |

---

## 5. ROI 調校設計

### 5.1 ROI 調校 UI 流程

ROI 調校是 L3 調校模式的核心功能。流程如下：

```
1. 使用者進入 L3 調校模式
2. 選擇要調校的 region（Serial / Drawing）
3. 系統載入多頁採樣（4~8 頁，均勻取樣）
4. 使用者在任一採樣頁上拖曳 ROI 框
5. 系統即時更新所有採樣頁的裁切預覽 + confidence
6. 使用者滿意後點「套用 ROI 並重跑 batch」
7. 系統儲存新 profile + 重新執行 batch detect
```

### 5.2 多頁採樣策略

```python
def sample_pages_for_calibration(
    page_folder: Path,
    total_pages: int,
    sample_count: int = 6,
) -> list[Path]:
    """均勻取樣，包含首頁、末頁、和中間頁"""
    if total_pages <= sample_count:
        return sorted(page_folder.glob("*.pdf"))
    step = total_pages // (sample_count - 1)
    indices = [0] + [i * step for i in range(1, sample_count - 1)] + [total_pages - 1]
    pages = sorted(page_folder.glob("*.pdf"))
    return [pages[i] for i in indices]
```

多頁採樣結果顯示在 L3 中欄的 **ROI Editor** tab：

```
┌─────────────────────────────────────────┐
│  多頁採樣預覽（Serial Region）             │
│                                         │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐           │
│  │ p1 │ │ p8 │ │p16 │ │p24 │           │
│  │[17]│ │[08]│ │[16]│ │[??]│           │
│  │0.94│ │0.91│ │0.87│ │0.41│           │
│  │ ✓  │ │ ✓  │ │ ✓  │ │ ⚠  │           │
│  └────┘ └────┘ └────┘ └────┘           │
│                                         │
│  ┌────┐ ┌────┐                         │
│  │p32 │ │p42 │                         │
│  │[32]│ │[42]│                         │
│  │0.93│ │0.95│                         │
│  │ ✓  │ │ ✓  │                         │
│  └────┘ └────┘                         │
│                                         │
│  平均信心: 0.85  命中率: 5/6            │
└─────────────────────────────────────────┘
```

每張採樣卡片包含：
- 頁碼
- Serial region 裁切圖（base64 PNG）
- 偵測到的 serial 值（若有）
- Confidence 值
- 狀態 icon（✓ >= threshold, ⚠ < threshold, 🚫 無結果）

### 5.3 ROI Overlay Preview

在 L3 右欄的 PDF 全頁預覽上，疊加兩個 ROI 框：

```
┌──────────────────────┐
│                      │
│  ┌─ ─ ─ ─ ─ ┐       │  ← Serial ROI (藍色虛線框)
│  │  17      │       │     可拖曳四角和邊緣
│  └─ ─ ─ ─ ─ ┘       │
│                      │
│                      │
│         ┌─ ─ ─ ─ ─ ┐│  ← Drawing ROI (綠色虛線框)
│         │  PIPE-A  ││     可拖曳四角和邊緣
│         └─ ─ ─ ─ ─ ┘│
│                      │
└──────────────────────┘
```

與 PyQt6 `RegionSelector` 的互動模型一致：
- 點擊 ROI 框內部 → `move` 模式
- 點擊四角 handle → `resize` 模式
- 拖曳中 emit `regionChanged` → 即時更新裁切預覽
- 放開 emit `regionCommitted` → 觸發所有採樣頁重新裁切 + 偵測

### 5.4 Confidence Heatmap（Developer Mode Only）

將 confidence 值視覺化疊加在 PDF 預覽上：

```python
def render_confidence_heatmap(
    page_image: QImage,
    serial_region: SerialVisionRegion,
    confidence: float,
) -> bytes:
    """在 serial region 上疊加 confidence 色塊"""
    # 高信心(>=0.90) → 半透明綠
    # 中信心(0.70~0.90) → 半透明黃
    # 低信心(<0.70) → 半透明紅
    # 無結果 → 半透明灰
```

React 端用 CSS `background-color` + `opacity` 實現，不需要 canvas：

```tsx
<div className="roi-overlay" style={{
  left: `${region.left * 100}%`,
  top: `${region.top * 100}%`,
  width: `${region.width * 100}%`,
  height: `${region.height * 100}%`,
  backgroundColor: confidenceColor(confidence),
  opacity: 0.3,
}} />
```

### 5.5 Profile Presets

| Preset | Serial Region | Drawing Region | 適用場景 |
|--------|--------------|----------------|---------|
| **default** | L:0.62 T:0.00 W:0.38 H:0.24 | L:0.50 T:0.66 W:0.50 H:0.34 | 標準 ISO 圖紙（流水號右上角） |
| **full_top** | L:0.50 T:0.00 W:0.50 H:0.20 | L:0.50 T:0.66 W:0.50 H:0.34 | 流水號在標題列右半部 |
| **title_block** | L:0.60 T:0.88 W:0.40 H:0.12 | L:0.00 T:0.88 W:0.60 H:0.12 | 流水號在圖框右下角標題欄 |
| **custom** | 使用者自訂 | 使用者自訂 | 特殊格式 |

Preset 選擇器放在 L3 左欄 Profile 區域，下拉選單：

```
Profile: [default ▼]
  ○ default — 標準 ISO 圖紙
  ○ full_top — 流水號在標題列
  ○ title_block — 圖框標題欄
  ● custom — 自訂（目前使用中）
```

### 5.6 Per-Project Profile

Profile 以**資料夾**為 key 儲存，沿用現有 `AppStateStore.iso_naming_profile(folder)` 機制：

```python
# 儲存路徑
state_store.set_iso_naming_profile(
    folder=work_folder,
    payload=profile.to_payload()
)

# state.json 中的結構
{
  "iso_profiles": {
    "D:\\Projects\\ISO-2026-001": {
      "serial_region": { ... },
      "drawing_region": { ... },
      "confidence_threshold": 0.70,
      "pattern": "{serial}--{line}.pdf",
      "preset_name": "custom",
      "version": 2,
      "updated_at": "2026-06-08T12:34:05"
    }
  }
}
```

### 5.7 避免調校污染一鍵預設值

| 機制 | 說明 |
|------|------|
| **Preset lock** | 選擇 preset (非 custom) 時，ROI editor 為唯讀，需先點「建立自訂副本」才能編輯 |
| **Profile version** | 每次儲存 profile 時 `version += 1`，保留 `previous_version` 供回退 |
| **One-click 隔離** | L1 一鍵模式**只讀** profile，不寫入。即使使用者從 L3 改了 profile，L1 下次執行時用的是最新儲存的 profile，但不會在 L1 中觸發任何 profile 修改 |
| **Reset button** | L3 有「重設為預設」按鈕，將 serial_region 和 drawing_region 恢復為 `IsoNamingProfile` 的 dataclass default |

### 5.8 回復上一版設定

```python
# launcher/core/state_store.py
def iso_profile_history(self, folder: str | Path) -> list[dict]:
    """取得指定資料夾的 profile 歷史（最多 5 版）"""
    ...

def restore_iso_profile(self, folder: str | Path, version: int) -> IsoNamingProfile:
    """回復到指定版本的 profile"""
    ...
```

儲存結構：
```json
{
  "iso_profiles": {
    "D:\\Projects\\ISO-2026-001": { "version": 3, ... }
  },
  "iso_profile_history": {
    "D:\\Projects\\ISO-2026-001": [
      { "version": 2, "updated_at": "...", "serial_region": { ... }, ... },
      { "version": 1, "updated_at": "...", "serial_region": { ... }, ... }
    ]
  }
}
```

---

## 6. 工作台狀態機

### 6.1 狀態定義

```typescript
type WorkbenchState =
  | "waiting"          // 等待使用者選擇資料夾
  | "input_ready"      // 來源已選，尚未產生 plan
  | "draft_generating" // 正在執行 batch detect / plan
  | "draft_ready"      // plan 產生完成，全部 ready
  | "warn"             // plan 產生完成，有 warn 列
  | "blocked"          // plan 產生完成，有 blocked 列
  | "manual_review"    // 使用者正在修正問題列
  | "ready_to_apply"   // 所有問題已修正，可以套用
  | "applying"         // 正在執行更名
  | "applied"          // 更名完成
  | "failed"           // 某個階段失敗
  | "replaying"        // 正在重播之前的 run log
  | "tuning"           // L3 調校模式中
```

### 6.2 狀態轉換圖

```
                         ┌──────────────┐
                         │   waiting    │
                         └──────┬───────┘
                                │ 選擇資料夾 + discover 成功
                                ▼
                         ┌──────────────┐
                    ┌───>│ input_ready  │<────────────────────┐
                    │    └──────┬───────┘                     │
                    │           │ 按下「產生草稿」或「一鍵命名」│
                    │           ▼                             │
                    │    ┌──────────────────┐                 │
                    │    │ draft_generating │                 │
                    │    └──────┬───────────┘                 │
                    │           │ batch detect 完成            │
                    │     ┌─────┼─────┐                       │
                    │     │     │     │                       │
                    │     ▼     ▼     ▼                       │
                    │  ┌─────┐┌────┐┌───────┐                │
                    │  │draft││warn││blocked│                │
                    │  │ready││    ││       │                │
                    │  └──┬──┘└─┬──┘└──┬────┘                │
                    │     │     │      │                      │
                    │     │     │      │ 使用者點「修正」       │
                    │     │     │      ▼                      │
                    │     │     │  ┌──────────────┐           │
                    │     │     └─>│manual_review │           │
                    │     │        └──────┬───────┘           │
                    │     │               │ 所有問題修正完畢   │
                    │     │               ▼                   │
                    │     │        ┌──────────────┐           │
                    │     └───────>│ready_to_apply│<──────────┘
                    │              └──────┬───────┘
                    │                     │ 按下「套用更名」
                    │                     ▼
                    │              ┌──────────────┐
                    │              │   applying   │
                    │              └──────┬───────┘
                    │                ┌────┴────┐
                    │                ▼         ▼
                    │         ┌─────────┐ ┌────────┐
                    │         │ applied │ │ failed │
                    │         └─────────┘ └────┬───┘
                    │                          │ 重試
                    └──────────────────────────┘
```

### 6.3 每個狀態的 UI 行為

#### `waiting`

| 項目 | 內容 |
|------|------|
| **UI** | L1: 空 pipeline + 大按鈕「選擇資料夾」。L2/L3: 空白 plan table + 提示文字 |
| **可用按鈕** | 「選擇資料夾」 |
| **禁用按鈕** | 所有其他按鈕 |
| **下一步** | 選擇資料夾 → `input_ready` |
| **回到安全** | 已在安全狀態 |

#### `input_ready`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline step 1 ✓，按鈕變為「一鍵命名」。L2: 左欄來源已填，checklist 部分 ✓ |
| **可用按鈕** | 「一鍵命名」/「產生草稿」/「重新選擇資料夾」 |
| **禁用按鈕** | 「套用更名」/「匯出 CSV」/「批次判讀」（尚未有 plan） |
| **下一步** | 按「一鍵命名」→ `draft_generating` |
| **回到安全** | 按「重新選擇資料夾」→ `waiting` |

#### `draft_generating`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline step 3 `running` 動畫，event log 即時更新，大按鈕變為「取消」。L2: plan table 顯示 loading skeleton。L3: Job Protocol 面板顯示進度 |
| **可用按鈕** | 「取消」 |
| **禁用按鈕** | 所有其他按鈕 |
| **下一步** | 完成 → `draft_ready` / `warn` / `blocked`；失敗 → `failed` |
| **回到安全** | 按「取消」→ `input_ready` |

#### `draft_ready`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline 全綠，底部摘要「42 可更名」，大按鈕變為「一鍵套用」。L2: plan table 全 ready 狀態 |
| **可用按鈕** | 「一鍵套用」/「匯出 CSV」/「匯出 Run Log」/「重新產生」 |
| **禁用按鈕** | 無 |
| **下一步** | 按「一鍵套用」→ `applying` |
| **回到安全** | 按「重新產生」→ `draft_generating` |

#### `warn`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline step 4 黃色，底部摘要「38 可更名、3 需確認」，出現「查看問題列」和「匯出問題包」按鈕。L2: plan table 有黃色列 |
| **可用按鈕** | 「查看問題列」→ 切換到 L2 /「匯出問題包」/「重新產生」 |
| **禁用按鈕** | 「一鍵套用」（不能直接套用有 warn 的結果） |
| **下一步** | 按「查看問題列」→ `manual_review`（自動切換到 L2） |
| **回到安全** | 按「重新產生」→ `draft_generating` |

#### `blocked`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline step 4 紅色，底部摘要「1 阻擋」。L2: plan table 有紅色列，`P13 阻擋列說明` 展開 |
| **可用按鈕** | 「查看問題列」/「匯出問題包」/「重新產生」 |
| **禁用按鈕** | 「一鍵套用」 |
| **下一步** | 按「查看問題列」→ `manual_review` |
| **回到安全** | 修正後 → `warn` 或 `ready_to_apply` |

#### `manual_review`

| 項目 | 內容 |
|------|------|
| **UI** | L2: plan table 篩選為「只看問題列」，右欄 Visual Inspector 顯示目前問題列的 PDF 預覽，「採用判讀值」/「確認此列」/「下一個問題」按鈕可用 |
| **可用按鈕** | 「採用判讀值」/「確認此列」/「下一個問題」/inline 編輯/「重新產生」 |
| **禁用按鈕** | 「一鍵套用」（直到所有問題修正完畢） |
| **下一步** | 所有問題修正完畢 → `ready_to_apply` |
| **回到安全** | 按「重新產生」→ `draft_generating` |

#### `ready_to_apply`

| 項目 | 內容 |
|------|------|
| **UI** | L2: plan table 全綠，底部顯示「套用更名」primary 按鈕亮起 |
| **可用按鈕** | 「套用更名」/「匯出 CSV」/「重新產生」 |
| **禁用按鈕** | 無 |
| **下一步** | 按「套用更名」→ 彈出 `IsoDryRunDialog` 確認 → `applying` |
| **回到安全** | 按「重新產生」→ `draft_generating` |

#### `applying`

| 項目 | 內容 |
|------|------|
| **UI** | 全按鈕禁用，顯示進度動畫。L2: plan table 逐列變為「已更名」狀態 |
| **可用按鈕** | 無（不可取消更名操作） |
| **禁用按鈕** | 全部 |
| **下一步** | 完成 → `applied`；失敗 → `failed` |
| **回到安全** | 無法中斷（檔案更名是原子操作） |

#### `applied`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline 全綠 + ✓，大按鈕變為「完成」。L2: plan table 顯示「已更名」+ 綠色勾號 |
| **可用按鈕** | 「匯出 Run Log」/「匯出 CSV」/「關閉」/「新任務」 |
| **禁用按鈕** | 「套用更名」/「重新產生」 |
| **下一步** | 按「新任務」→ `waiting` |
| **回到安全** | 已在終態 |

#### `failed`

| 項目 | 內容 |
|------|------|
| **UI** | L1: pipeline 失敗階段紅色，底部顯示 error summary +「匯出問題包」+「重試」。L2: error banner + run log |
| **可用按鈕** | 「匯出問題包」/「重試」/「回到選擇資料夾」/「開啟調校工作台」 |
| **禁用按鈕** | 「套用更名」 |
| **下一步** | 按「重試」→ `draft_generating`；按「開啟調校工作台」→ 切換 L3 + `tuning` |
| **回到安全** | 按「回到選擇資料夾」→ `waiting` |

#### `replaying`

| 項目 | 內容 |
|------|------|
| **UI** | L2/L3: Run History tab 顯示正在重播的 run log，plan table 從 run log 還原 |
| **可用按鈕** | 「取消重播」 |
| **禁用按鈕** | 所有修改類按鈕 |
| **下一步** | 完成 → `warn` / `blocked` / `draft_ready`（取決於原 run log 的結果） |
| **回到安全** | 按「取消重播」→ `input_ready` |

#### `tuning`

| 項目 | 內容 |
|------|------|
| **UI** | L3: ROI Editor 啟用，多頁採樣顯示，滑桿可用 |
| **可用按鈕** | 「套用 ROI 並重跑」/「重設為預設」/「自動校準」/「載入 preset」 |
| **禁用按鈕** | 「套用更名」 |
| **下一步** | 按「套用 ROI 並重跑」→ `draft_generating`（用新 ROI 重跑 batch） |
| **回到安全** | 按「取消」→ `input_ready` |

---

## 7. 一鍵失敗後的導流

### 7.1 失敗情境分類

| 情境 | 嚴重度 | L1 顯示 | 導流目標 |
|------|--------|---------|---------|
| 資料夾無 PDF | 🚫 blocked | 「找不到 PDF 檔案。請確認資料夾內容。」 | 無（使用者自行檢查） |
| 無 ISO List | 🚫 blocked | 「找不到 ISO 清單。請確認資料夾中有 .xlsx 或 .csv 檔案。」 | 無 |
| PDF 無法開啟 | 🚫 blocked | 「PDF 檔案無法開啟，可能已損壞或加密。」 | 無 |
| OCR 未安裝 | ⚠ warn | 「判讀工具未安裝。可嘗試純文字命名或聯絡工程師安裝。」 | L3 |
| Batch detect 部分失敗 | ⚠ warn | 「{n} 頁判讀失敗，{m} 頁需確認。」 | L2 |
| Batch detect 全部失敗 | 🚫 blocked | 「所有頁面判讀失敗。可能是 PDF 格式不支援。」 | L3 |
| Apply 部分失敗 | ⚠ warn | 「{n} 個檔案更名失敗（可能被其他程式佔用）。」 | L2 |
| 未知 exception | 🚫 blocked | 「發生未預期的錯誤。」 | 匯出 debug bundle |

### 7.2 L1 失敗畫面

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Pipeline: [✓來源] → [✓拆頁] → [🚫判讀] → [○] → [○] → [○] │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ⚠️ 一鍵命名遇到問題                                  │    │
│  │                                                     │    │
│  │  38 頁判讀成功，3 頁需要確認，1 頁判讀失敗。           │    │
│  │                                                     │    │
│  │  你可以：                                            │    │
│  │                                                     │    │
│  │  ┌─────────────────────────┐  ┌──────────────────┐  │    │
│  │  │  📋 查看並修正問題列      │  │  📦 匯出問題包    │  │    │
│  │  │  開啟工作台，逐列檢查     │  │  交給工程師診斷    │  │    │
│  │  └─────────────────────────┘  └──────────────────┘  │    │
│  │                                                     │    │
│  │  ┌─────────────────────────┐  ┌──────────────────┐  │    │
│  │  │  🔄 重試                 │  │  ← 重新選擇資料夾  │  │    │
│  │  └─────────────────────────┘  └──────────────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  Event Log:                                                 │
│  ▸ 12:34:10  [error] page 37: serial not detected           │
│  ▸ 12:34:08  [warn]  page 23: confidence 0.62 < 0.70       │
│  ▸ 12:34:05  [ok]    page 22: serial=16 confidence=0.91     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**設計要點：**
- 一般使用者看到的第一行文字是**白話摘要**，不含任何技術名詞
- 四個按鈕按推薦程度排列：「查看並修正問題列」最突出（primary），「匯出問題包」次之（secondary）
- Event log 只在底部小區域顯示最近 3 條，不搶注意力
- 「查看並修正問題列」→ 切換到 L2 `manual_review` 狀態，自動篩選問題列
- 「匯出問題包」→ 產生 debug bundle zip → 複製檔案路徑到剪貼簿 → 顯示「已複製路徑，可貼給工程師」

### 7.3 工程師接手流程

工程師收到 debug bundle 後：

1. **解開 zip** → 讀取 `run_log.json`
2. **在工作台開啟 Run History** → 點「匯入 Run Log」→ 從 JSON 還原 plan table 和 profile
3. **查看 pilot results** → 定位失敗的 pilot item
4. **切換到 L3 調校** → 調整 ROI / threshold / engine
5. **重跑 batch detect** → 驗證修正效果
6. **回到 L2 套用** → 完成更名

**Replay 功能**：工程師可以在 L2 的 Run History 中選擇一個 run log，點「從此紀錄重播」，系統會：
- 載入 run log 中的 `input` 和 `profile`
- 還原 plan table（從 `rows`）
- 進入 `replaying` 狀態
- 工程師可以在此基礎上修改 profile 後重跑

### 7.4 「開啟調校工作台」按鈕

此按鈕只在以下情況出現：
- L1 失敗畫面（見上圖）
- L2 的 `blocked` 或 `failed` 狀態
- L2 Run History 中選了一個 `failed` 的 run log

按鈕行為：
1. 切換 `isoView` 到 `"engineer"`
2. 設定 `workbenchState` 到 `"tuning"`
3. 自動載入失敗 run log 的 profile
4. 自動觸發多頁採樣

---

## 8. 測試策略

### 8.1 測試矩陣

#### 一鍵 Happy Path

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T01 | 標準 42 頁 PDF + 完整 ISO List → 全部 ready → 自動套用 | integration | L1 | discover → split → detect → plan → apply |
| T02 | 已有 `_pages` 資料夾 → 跳過拆頁 → 直接判讀 | integration | L1 | P03 skip path |
| T03 | 檔名已符合 `{serial}--{line}.pdf` → 跳過 vision | unit | backend | P06 skip path |
| T04 | ISO List 為 CSV (cp950 編碼) → 正確解析 | unit | backend | P04 encoding |
| T05 | 中文路徑 subprocess UTF-8 傳遞 | integration | backend | Windows codepage |

#### 一鍵失敗但可產生 Log

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T06 | 3 頁低信心 + 1 頁無結果 → run log 含 warn/blocked 分類 | integration | L1→L2 | P06, P08, P12, P13 |
| T07 | Batch detect 中途取消 → run log 記錄 partial result | integration | backend | cancel.json |
| T08 | Apply 時第 5 個檔案被鎖定 → partial apply + exception log | integration | backend | P15, Windows file lock |
| T09 | ISO List 有 42 筆但 PDF 只有 40 頁 → P10 缺漏偵測 | unit | backend | P10 |
| T10 | Pattern 產生非法檔名 → P11 blocked | unit | backend | P11 |

#### 工作台讀取 Log

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T11 | 匯入 run log JSON → plan table 正確還原 | unit | frontend | replay |
| T12 | Run log 含 exception → error banner 顯示 user_summary | unit | frontend | error display |
| T13 | Pilot results 渲染正確（✓/⚠/🚫 狀態） | unit | frontend | P01~P17 UI |
| T14 | 從 run log 還原 profile → L3 ROI editor 顯示正確的 region | integration | L3 | profile restore |

#### ROI 調整後重新產生 Draft

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T15 | 修改 serial_region → batch detect 用新 ROI → confidence 提升 | integration | L3 | ROI update |
| T16 | 自動校準成功 → region 更新 → profile 自動儲存 | unit | backend | P17 |
| T17 | 多頁採樣 API 回傳正確的 sample pages | unit | backend | sampling |
| T18 | Profile preset 切換 → region 正確替換 | unit | frontend | preset |

#### Blocked Rows Manual Correction

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T19 | Inline 改 serial → new_name 自動重算 → status 更新 | unit | frontend | P14 |
| T20 | 採用判讀值 → serial 填入 → ISO list lookup → line_no 填入 | unit | frontend | P07, P14 |
| T21 | 確認此列 → review issue 清除 → 問題列計數減少 | unit | frontend | P14 |
| T22 | 「只看問題列」filter → 修正完最後一列 → filter 自動關閉 | unit | frontend | filter |

#### Dry-Run / Apply / Rollback

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T23 | Dry-run dialog 顯示正確的 will-rename 表格 | unit | frontend | P15 |
| T24 | Apply 全部成功 → run log 追加 apply_result | integration | backend | P15 |
| T25 | Apply 部分失敗 → run log 含 partial_result + exception | integration | backend | P15 |
| T26 | Rollback：從 CSV 反向 rename → 原始檔名恢復 | integration | backend | P15 rollback |

#### Profile Save / Load

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T27 | Save profile → state.json 正確寫入 | unit | backend | P17 |
| T28 | Load profile → 所有欄位正確還原 | unit | backend | P17 |
| T29 | Profile history → 儲存 3 版後可回復到第 1 版 | unit | backend | P17 history |
| T30 | Profile 損壞 → fallback 到預設值 + warn | unit | backend | P17 recovery |

#### Edge Cases

| # | 測試名稱 | 類型 | 層級 | 涵蓋 |
|---|---------|------|------|------|
| T31 | Malformed ISO List（空 sheet、header 在 row 25） | unit | backend | P04 |
| T32 | Missing pages（page folder 缺少 p005.pdf） | unit | backend | P03, P10 |
| T33 | Duplicate serial（ISO List 有兩列 serial=5） | unit | backend | P09 |
| T34 | OCR confidence < 0.30（極度模糊的 PDF） | unit | backend | P06, P08 |
| T35 | 路徑含中文 + 特殊字元（`ISO 圖紙 (2026) #3`） | integration | backend | encoding |
| T36 | Windows file locked（用 ProcessGuard 模擬） | integration | backend | P15 |
| T37 | Tauri browser fallback vs native（ISO surface 載入） | e2e | frontend | Tauri |

### 8.2 測試分層

| 層級 | 命令 | 數量 | 執行時間 | CI 適合 |
|------|------|------|---------|---------|
| `unit-backend` | `pytest tests/test_iso_*.py tests/test_tauri_iso_*.py tests/test_serial_*.py tests/test_batch_*.py tests/test_region_*.py` | ~55 | <30s | ✅ |
| `unit-frontend` | `npx vitest run` | ~15 (待建) | <15s | ✅ |
| `integration` | `pytest tests/test_tauri_iso_workflow.py -k "subprocess or worker"` | ~5 | <60s | ✅ |
| `e2e-playwright` | `npx playwright test` | ~5 (待建) | <120s | ⚠ Windows runner |
| `manual-smoke` | 人工操作 L1 → L2 → L3 完整流程 | 1 | 5~10min | ❌ 本機 |

### 8.3 測試資料 (Fixtures)

```
tests/fixtures/iso/
├── standard_42/
│   ├── combine.pdf          # 42 頁標準測試 PDF（流水號清晰）
│   ├── iso_list.xlsx        # 42 筆完整 ISO List
│   └── expected_plan.json   # 預期的 plan 輸出
├── low_confidence/
│   ├── blurry.pdf           # 模糊流水號
│   └── iso_list.xlsx
├── malformed/
│   ├── empty_sheet.xlsx     # 空 sheet
│   ├── no_header.csv        # 無 header 列
│   └── wrong_encoding.csv   # 非 UTF-8 且無 BOM
├── chinese_path/
│   └── ISO 圖紙 (2026)/     # 中文路徑測試
│       ├── combine.pdf
│       └── iso_list.xlsx
├── duplicate_serial/
│   ├── combine.pdf
│   └── iso_list_dup.xlsx    # serial 5 出現兩次
├── missing_pages/
│   ├── combine_40.pdf       # 只有 40 頁
│   └── iso_list_42.xlsx     # ISO List 有 42 筆
└── locked_file/
    ├── combine.pdf
    └── iso_list.xlsx        # 搭配 ProcessGuard 模擬鎖定
```

---

## 9. 建議模組 / 檔案結構

### 9.1 React Components

```
frontend/tauri-spike/src/
├── surfaces/
│   └── IsoPdfAutopilot/
│       ├── index.tsx                  # 主元件，管理 isoView + workbenchState
│       ├── OneClickSurface.tsx        # L1 一鍵模式
│       ├── WorkbenchSurface.tsx       # L2 工作台模式
│       ├── EngineerSurface.tsx        # L3 調校模式
│       └── shared/
│           ├── PipelineStepper.tsx    # 六階段 pipeline 視覺化
│           ├── EventLog.tsx           # event log terminal
│           ├── ResultSummary.tsx      # 結果摘要卡片
│           └── FailureActions.tsx     # 失敗後的動作按鈕
│
├── iso/
│   ├── IsoPlanTable.tsx               # Plan Table（L2 中欄）
│   ├── IsoVisualPanel.tsx             # PDF 預覽 + ROI + 裁切（L2/L3 右欄）
│   ├── IsoDryRunDialog.tsx            # 套用前確認 dialog
│   ├── IsoResultDialog.tsx            # 命名草稿結果 dialog
│   ├── ChecklistGate.tsx              # 一鍵 review 階段 checklist
│   ├── SourcePanel.tsx                # 來源選擇面板（L2 左欄）
│   ├── MappingPanel.tsx              # ISO List mapping（L2 左欄）
│   ├── PilotList.tsx                  # Pilot List 渲染（L2 Run History）
│   ├── RunHistoryPanel.tsx           # Run log 列表 + 匯入/重播
│   ├── RoiEditor.tsx                  # ROI 拖曳編輯器（L3）
│   ├── MultiPageSampler.tsx          # 多頁採樣顯示（L3）
│   ├── ConfidenceHeatmap.tsx         # Confidence heatmap（L3 dev）
│   ├── DiagnosticPanel.tsx           # Raw diagnostic JSON（L3 dev）
│   ├── ProfilePanel.tsx              # Profile 管理（L3 左欄）
│   ├── DebugBundleExport.tsx         # 匯出 debug bundle
│   └── shared/
│       ├── RoiBox.tsx                 # ROI 矩形框（overlay）
│       ├── PreviewCrop.tsx           # 裁切圖顯示
│       ├── StatusChip.tsx            # 狀態 chip（ready/warn/blocked/idle）
│       ├── ConfidenceChip.tsx        # 信心值 chip
│       └── PathPickerRow.tsx         # 路徑選擇列
│
├── hooks/
│   ├── useIsoWorkflow.ts             # ISO workflow state management
│   ├── useIsoOneClick.ts             # 一鍵流程邏輯
│   ├── useIsoBatchJob.ts             # Batch detect job polling
│   ├── useIsoPreview.ts              # PDF 預覽 + cache
│   ├── useIsoProfile.ts             # Profile load/save/history
│   ├── useIsoPlanTable.ts           # Plan table filter/sort/edit
│   ├── useIsoPilotList.ts           # Pilot list computation
│   ├── useIsoRunLog.ts              # Run log read/write/import/export
│   ├── useWorkbenchState.ts         # 狀態機管理
│   └── useRoiEditor.ts              # ROI drag/resize logic
│
├── schema/
│   ├── isoWorkflow.ts               # 現有，擴展 IPC types
│   ├── isoRunLog.ts                  # 【新增】Run Log TypeScript types
│   ├── isoPilotItem.ts              # 【新增】Pilot Item types
│   ├── isoProfile.ts                # 【新增】Profile types + presets
│   └── isoDebugBundle.ts            # 【新增】Debug Bundle types
│
├── isoWorkflow.ts                   # 現有 IPC 函式（搬入 schema/ 或保留）
├── legacy.ts                        # 現有
├── report.ts                        # 現有
└── styles.css                       # 現有（擴展 ISO 相關樣式）
```

### 9.2 Backend Python Modules

```
launcher/
├── app/
│   ├── tauri_iso_workflow.py         # 現有，擴展 run log 寫入
│   ├── tauri_iso_preview.py          # 現有，擴展多頁採樣
│   ├── tauri_iso_worker.py           # 現有
│   └── iso_run_log.py               # 【新增】Run Log 寫入/讀取/匯出
│
├── plugins/iso_tools/
│   ├── iso_naming.py                 # 現有
│   ├── serial_vision.py              # 現有
│   ├── serial_correction.py          # 現有
│   ├── profile.py                    # 現有，擴展 preset + version
│   ├── rename_plan.py                # 現有
│   ├── validator.py                  # 現有，擴展為 pilot list
│   ├── issues.py                     # 現有
│   ├── pilot_list.py                 # 【新增】Pilot Item 定義 + 執行
│   ├── roi_calibration.py            # 【新增】多頁採樣 + confidence 統計
│   ├── profile_presets.py            # 【新增】Preset 定義 + 管理
│   └── debug_bundle.py               # 【新增】Debug Bundle 匯出
│
├── core/
│   ├── paths.py                      # 現有
│   ├── state_store.py                # 現有，擴展 profile history
│   └── run_store.py                  # 【新增】Run Log 存檔/歸檔/清理
```

### 9.3 Profile Schema (擴展)

```python
# launcher/plugins/iso_tools/profile.py

@dataclass(frozen=True)
class IsoNamingProfile:
    serial_region: SerialVisionRegion = field(default_factory=...)
    drawing_region: SerialVisionRegion = field(default_factory=...)
    confidence_threshold: float = 0.70
    pattern: str = "{serial}--{line}.pdf"
    iso_list_path: Path | None = None
    sheet_name: str | None = None
    serial_col: int | None = None
    line_col: int | None = None
    # 【新增】
    preset_name: str = "default"       # "default" | "full_top" | "title_block" | "custom"
    version: int = 1                   # 每次儲存 +1
    updated_at: str | None = None      # ISO timestamp
```

### 9.4 Run Log Schema (TypeScript)

```typescript
// frontend/tauri-spike/src/schema/isoRunLog.ts

export interface IsoRunLog {
  schema_version: 2;
  run_id: string;
  timestamp: string;
  duration_ms: number;
  input: IsoRunInput;
  profile: IsoProfilePayload;
  pipeline: IsoPipeline;
  iso_table: IsoTableInfo;
  summary: IsoPlanSummary;
  pilot_results: PilotResult[];
  failed_stage: string | null;
  exception: IsoRunException | null;
  user_summary: string;
  developer_diagnostic: IsoDevDiagnostic;
  suggested_next_actions: SuggestedAction[];
  replay: IsoReplayInfo;
  rows: IsoPlanRow[];
  apply_result: IsoApplyResult | null;
}

export interface IsoPipeline {
  stages: PipelineStage[];
}

export interface PipelineStage {
  id: "discover" | "split" | "iso_parse" | "batch_detect" | "plan" | "apply";
  status: "ok" | "warn" | "failed" | "skipped" | "running" | "pending";
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  detail?: string;
}

export interface PilotResult {
  id: string;
  state: "success" | "warn" | "blocked" | "skipped" | "pending";
  detail: string;
}

export interface IsoRunException {
  type: string;
  message: string;
  traceback: string;
  file?: string;
  errno?: number;
}

export interface SuggestedAction {
  action: string;
  label: string;
  target_mode?: "workbench" | "engineer";
  detail?: string;
  condition?: string;
}
```

### 9.5 Tests

```
tests/
├── test_iso_naming.py                # 現有
├── test_iso_profile.py               # 現有，擴展 version/preset/history
├── test_iso_rename_plan.py           # 現有
├── test_iso_validator.py             # 現有，擴展 pilot list
├── test_serial_vision.py             # 現有
├── test_iso_vision_correction.py     # 現有
├── test_batch_detect_thread.py       # 現有
├── test_region_selector.py           # 現有
├── test_tauri_iso_workflow.py        # 現有，擴展 run log
├── test_tauri_iso_preview.py         # 現有，擴展 multi-page sampling
├── test_iso_pilot_list.py            # 【新增】Pilot item 定義 + 執行邏輯
├── test_iso_run_log.py               # 【新增】Run log 寫入/讀取/匯出/歸檔
├── test_iso_roi_calibration.py       # 【新增】多頁採樣 + confidence 統計
├── test_iso_profile_presets.py       # 【新增】Preset 切換 + profile history
├── test_iso_debug_bundle.py          # 【新增】Debug bundle zip 內容驗證
├── test_iso_run_store.py             # 【新增】Run store 歸檔/清理
├── test_iso_one_click_workflow.py    # 現有（PyQt6）
├── test_iso_autopilot_page.py        # 現有（PyQt6）
├── test_iso_preview_panel.py         # 現有（PyQt6）
├── test_iso_workflow_status.py       # 現有（PyQt6）
├── test_iso_review_filter.py         # 現有（PyQt6）
├── test_iso_result_dialog.py         # 現有（PyQt6）
├── test_iso_styles.py                # 現有（PyQt6）
├── test_iso_profile_dialog.py        # 現有（PyQt6）
│
├── fixtures/iso/                     # 【新增】測試資料目錄
│   ├── standard_42/
│   ├── low_confidence/
│   ├── malformed/
│   ├── chinese_path/
│   ├── duplicate_serial/
│   ├── missing_pages/
│   └── locked_file/
│
└── (frontend tests)
    ├── frontend/tauri-spike/tests/
    │   ├── iso/
    │   │   ├── IsoPlanTable.spec.ts       # 【新增】
    │   │   ├── IsoVisualPanel.spec.ts     # 【新增】
    │   │   ├── PipelineStepper.spec.ts    # 【新增】
    │   │   ├── PilotList.spec.ts          # 【新增】
    │   │   ├── RoiEditor.spec.ts          # 【新增】
    │   │   ├── OneClickSurface.spec.ts     # 【新增】
    │   │   └── useIsoWorkflow.spec.ts     # 【新增】
    │   └── smoke.spec.ts                  # 【新增】dock surface 載入
    └── (Playwright e2e)
        └── frontend/tauri-spike/e2e/
            └── iso-one-click.spec.ts      # 【新增】完整一鍵流程 e2e
```

### 9.6 Docs

```
docs/
├── iso_pdf_next_stage_design_2026-06-08.md   # 本文件
├── iso_pdf_workbench_audit.md                 # 現有
├── iso_pdf_workbench_next_stage_v0.1.md       # 現有
├── ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md  # 現有
├── codex_指令書_ISO一鍵工作台_重做_v0.1.md     # 現有
├── tauri_react_spike.md                       # 現有
└── iso_pilot_list_reference.md                # 【新增】Pilot List 快速參考卡
```

---

## 10. 優先級

### 10.1 現在就該做（本週 / 下週）

| # | 項目 | 範圍 | 原因 |
|---|------|------|------|
| 1 | **拆 App.tsx** — IsoPdfAutopilot 拆成獨立目錄 | React | 3036 行無法維護；拆出後 L1/L2/L3 各自一個檔案 |
| 2 | **定義 Run Log schema** — 在 `tauri_iso_workflow.py` 加入 `write_run_log()` | Python | 所有後續功能（replay、debug bundle、pilot list）都依賴 run log |
| 3 | **定義 IPC 合約 types** — `schema/isoRunLog.ts`, `schema/isoPilotItem.ts` | TypeScript | 防止 React/Python 兩端 quietly drift |
| 4 | **保護 L1 一鍵** — 確認 L1 畫面不含任何工程參數 | React | 最低風險、最高回報的 UX 改善 |
| 5 | **補 P09~P13 pilot items** — duplicate/missing/pattern/blocked/export | Python | 這些檢查目前散落在 `normalizeIsoRows()` 和 `_row_status()` 中，需要集中到 pilot list |
| 6 | **Run log 自動存檔** — `run_store.py` 寫入 + 歸檔 | Python | 不存 log 就無法 replay 或 debug |

### 10.2 一鍵更穩後做（原生 Tauri build 可成功之後）

| # | 項目 | 範圍 | 原因 |
|---|------|------|------|
| 7 | **L2 工作台完整 UI** — SourcePanel + MappingPanel + IsoPlanTable + IsoVisualPanel | React | 取代現有的 workbench view |
| 8 | **Run History + Replay** — 匯入 run log → 還原 plan table | React + Python | 工程師接手的關鍵路徑 |
| 9 | **Pilot List UI** — 在 Run History 中渲染 17 項 pilot results | React | 讓工作台有結構化的診斷能力 |
| 10 | **Debug Bundle 匯出** — `debug_bundle.py` + React `DebugBundleExport` | Python + React | 讓一般使用者能把問題交給工程師 |
| 11 | **Profile version + history** — `state_store.py` 擴展 | Python | 調校的安全性基礎 |
| 12 | **前端 Vitest 測試** — IsoPlanTable + PipelineStepper + useIsoWorkflow | TypeScript | React 端自動化測試的起點 |

### 10.3 工作台大改版時做

| # | 項目 | 範圍 | 原因 |
|---|------|------|------|
| 13 | **L3 調校模式完整 UI** — RoiEditor + MultiPageSampler + ProfilePanel | React | 需要 ROI overlay + 多頁採樣後端支援 |
| 14 | **多頁採樣後端** — `roi_calibration.py` + `tauri_iso_preview.py` 擴展 | Python | L3 的基礎設施 |
| 15 | **Confidence Heatmap** — `ConfidenceHeatmap.tsx` | React | Developer mode 進階功能 |
| 16 | **Preset 管理** — `profile_presets.py` + React ProfilePanel | Python + React | ROI 調校的使用者友善層 |
| 17 | **Playwright E2E** — `iso-one-click.spec.ts` | TypeScript | 完整流程自動化測試 |
| 18 | **狀態機形式化** — `useWorkbenchState.ts` 嚴格定義轉換規則 | React | 大改版需要可靠的狀態管理 |

### 10.4 等要正式包 exe 前做

| # | 項目 | 範圍 | 原因 |
|---|------|------|------|
| 19 | **Rollback 機制** — CSV-based reverse rename | Python | 生產環境的安全網 |
| 20 | **Sidecar 化 ISO workflow** — 編譯為獨立 exe 不依賴 `.venv` | Python + Rust | 減少 runtime 依賴 |
| 21 | **CI pipeline** — GitHub Actions: unit → integration → frontend → e2e | DevOps | 每次 commit 自動驗證 |
| 22 | **PyQt6 退出評估** — 逐功能確認 React parity | 全端 | 決定是否可以移除 PyQt6 |
| 23 | **Run log telemetry** — opt-in anonymous usage stats | Python | 了解真實世界的失敗模式 |
| 24 | **Localization** — 所有 userText 支援英文 | React | 國際化準備 |

---

## 附錄 A：與現有程式碼的對應關係

| 本文件概念 | 現有程式碼位置 | 需要的改動 |
|-----------|---------------|-----------|
| L1 一鍵模式 | `App.tsx` `isoView === "autopilot"` | 拆成 `OneClickSurface.tsx`，移除工程參數 |
| L2 工作台 | `App.tsx` `isoView === "workbench"` | 拆成 `WorkbenchSurface.tsx`，加入 Run History tab |
| L3 調校 | `App.tsx` `isoView === "engineer"` | 拆成 `EngineerSurface.tsx`，加入 ROI Editor |
| Plan Table | `IsoPlanTable` (in App.tsx) | 拆成 `iso/IsoPlanTable.tsx` |
| Visual Panel | `IsoVisualPanel` (in App.tsx) | 拆成 `iso/IsoVisualPanel.tsx` |
| Checklist | `validator.py` 7 items | 擴展為 `pilot_list.py` 17 items |
| Profile | `profile.py` `IsoNamingProfile` | 加 `preset_name`, `version`, `updated_at` |
| IPC | `isoWorkflow.ts` + `tauri_iso_workflow.py` | 加 `write_run_log` action |
| Batch job | `tauri_iso_worker.py` | 加 run log 增量寫入 |
| Preview | `tauri_iso_preview.py` | 加 multi-page sampling endpoint |
| Run Log | 不存在 | 新建 `iso_run_log.py` + `run_store.py` |
| Debug Bundle | 不存在 | 新建 `debug_bundle.py` |
| Pilot List | 不存在 | 新建 `pilot_list.py` |
| ROI Calibration | 不存在 | 新建 `roi_calibration.py` |
| Profile Presets | 不存在 | 新建 `profile_presets.py` |

## 附錄 B：現有 IPC Actions 與新增 Actions

| 現有 Action | 保留 | 新增 Action | 說明 |
|------------|------|------------|------|
| `discover_sources` | ✓ | — | |
| `split_pdf` | ✓ | — | |
| `load_iso_table` | ✓ | — | |
| `plan` | ✓ | — | 擴展 response 含 `pilot_results` |
| `build_rename_plan` | ✓ | — | |
| `export_plan_csv` | ✓ | — | |
| `start_batch_detect` | ✓ | — | 擴展 worker 寫入 run log |
| `job_status` | ✓ | — | |
| `cancel_job` | ✓ | — | |
| `apply` | ✓ | — | 擴展 response 含 `apply_result` |
| `load_profile` | ✓ | — | 擴展 response 含 `version`, `preset_name` |
| `save_profile` | ✓ | — | 擴展 request 含 `preset_name` |
| — | — | `write_run_log` | 寫入/更新 run log |
| — | — | `read_run_log` | 讀取指定 run_id 的 run log |
| — | — | `list_run_logs` | 列出最近 N 筆 run log |
| — | — | `export_debug_bundle` | 匯出 debug bundle zip |
| — | — | `sample_pages` | 多頁採樣（L3 用） |
| — | — | `restore_profile` | 回復到指定版本的 profile |
| — | — | `list_profile_history` | 列出 profile 歷史 |
| — | — | `dry_run_apply` | 試跑套用（不實際更名） |
