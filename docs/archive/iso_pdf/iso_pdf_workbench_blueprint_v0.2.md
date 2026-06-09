# ISO PDF 拆頁命名 — 下一階段先導計畫 v0.2

> 建立日期：2026-06-08
> 對接代碼：`launcher/app/tauri_iso_workflow.py`(1141行)、`launcher/app/tauri_iso_preview.py`(182行)、`frontend/tauri-spike/src/isoWorkflow.ts`(333行)、`launcher/plugins/iso_tools/`（iso_naming/serial_vision/serial_correction/profile/validator）、`launcher/ui/iso_pdf_naming_dialog.py`(2708行, legacy PyQt)
> 對接文件：`docs/ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md`（parity checklist）、`docs/iso_pdf_workbench_next_stage_v0.1.md`（Autopilot/Workbench 產品分層）
> 原則：一鍵功能保護不變複雜。工作台可以複雜但有清楚層級。所有建議須落地到 Windows + Tauri + Python。

---

## 1. 角色與產品邊界

### 1.1 三層模式

| 模式 | 使用者 | 目標 | 可見資訊 | 可執行動作 |
|------|--------|------|---------|-----------|
| **一鍵 (Autopilot)** | 長官、一般同事 | 3 步驟完成命名 | 來源摘要、checklist 燈號、一顆主按鈕、結果摘要 | 選資料夾 → 按一鍵 → 看結果 → 套用 |
| **工作台 (Workbench)** | 日常執行者、校對者 | 逐列確認、修問題、套用 | 命名表(全欄)、PDF 校對(含 ROI 裁切)、問題過濾、事件 log | 編輯欄位、看圖確認、標記已複核、套用勾選列 |
| **調校 (Engineer)** | 開發者、工程師、問題排查者 | 診斷、調整、修正、重跑 | 完整 pilot list、ROI 拖框校準、profile 管理、OCR 參數、ISO 對映、run log、debug bundle | 所有參數自由調整、重跑 pipeline、匯出診斷包 |

### 1.2 一鍵應保留的操作

- 選擇工作資料夾（自動發現 combine PDF + page folder + ISO list）
- 查看 checklist（紅黃綠燈號）
- 按一顆主按鈕「開始一鍵命名」
- 查看結果摘要（成功 N / 警告 M / 阻擋 K）
- 套用更名（勾選 ready + warn 列）
- 匯出 CSV 留底

### 1.3 一鍵絕對不該出現的

- ROI left/top/width/height 數字 slider
- OCR confidence threshold 調整
- ISO 欄位手動對應下拉
- sheet 選擇器（自動選）
- naming pattern 編輯
- 任何「工程師」「調校」「Debug」字樣的按鈕
- pilot list / run log / error traceback

### 1.4 三層間的導航

```
一鍵失敗 → [開啟工作台查看問題] 按鈕 → 工作台（命名表 + PDF 校對）
工作台修不好 → [開啟調校模式] 按鈕 → 調校（Engineer tabs）
調校修好 → [返回工作台] → 重新產生 draft → [返回一鍵]
```

三個模式共用同一份 plan 資料 (`IsoWorkflowPlan`)，切換不遺失狀態。

---

## 2. 建議資訊架構

### 2.1 整體版面（工作台模式，1180×760）

```
┌ 頂列: 模式切換 [一鍵 | 工作台 | 調校] · 步驟指示器 · 情境主按鈕 ─────────────┐
├ 左:設定軌(可收合) ┬ 中:命名表(主,~46%) ┬ 右:PDF校對/校準(~38%) ┤
│ ▸ 來源(folder/PDF)│ 搜尋 [________]   │ ┌ 整頁 PDF(大) ──────┐ │
│ ▸ ISO(list/sheet) │ [✓只看問題]        │ │                     │ │
│ ▸ 判讀(toggle)    │                    │ │                     │ │
│ ▸ Checklist(燈號) │ page│old name│ser… │ │                     │ │
│ [產生草稿後自動   │ ────┼────────┼───── │ └─────────────────────┘ │
│  收成摘要 chip]    │  1  │p001.p…│001  │ ┌ 流水號ROI(可拖框)──┐ │
│                   │  2  │p002.p…│002  │ │ 判讀: 002 (0.94)   │ │
│                   │  3  │p003.p…│⚠️003│ │ [採用] [重判]       │ │
│                   │ ...  │       │     │ └────────────────────┘ │
│                   │                    │ ┌ 圖號ROI(可拖框)────┐ │
│                   │                    │ │                    │ │
│                   │                    │ └────────────────────┘ │
│                   │                    │ 逐列:[確認此列][下一問題]│
├ 底:事件 log(可收合,預設一行高) ─────────────────────────────────────┤
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 調校模式 — Tab 分頁

調校模式使用 6 個 Tab：

| Tab | 內容 | 對應 pilot items |
|-----|------|-----------------|
| **來源診斷** | PDF 來源、拆頁結果、page count、missing pages | P01-P03 |
| **ISO 對映** | ISO list 解析、sheet/欄位/樣本值、column mapping | P04-P05 |
| **ROI 校準** | 流水號 ROI 拖框、圖號 ROI 拖框、多頁採樣、confidence heatmap | P06-P08 |
| **命名規則** | pattern editor、naming preview、duplicate detection | P10-P11 |
| **Pilot List** | 完整 pilot 清單、每項狀態、可展開細節 | 全部 |
| **Run Log** | 歷次 run log、exception stack、replay 按鈕、export debug bundle | — |

### 2.3 何時顯示什麼（visibility rules）

| 元素 | 一鍵 | 工作台 | 調校 |
|------|------|--------|------|
| 來源摘要 chip | ✅ | ✅（預設收合） | ✅ |
| Checklist 燈號 | ✅ | ✅（精簡） | ✅ |
| 命名表 | ❌ | ✅ | ✅ |
| PDF 預覽（唯讀） | ❌ | ✅ | ✅ |
| ROI 拖框校準 | ❌ | ❌ | ✅ |
| ISO 欄位手動選擇 | ❌ | ✅ | ✅ |
| Pattern editor | ❌ | ❌ | ✅ |
| OCR confidence slider | ❌ | ❌ | ✅ |
| Pilot list | ❌ | ❌ | ✅ |
| Run log viewer | ❌ | ❌ | ✅ |
| Event log（底部） | ✅（精簡） | ✅ | ✅ |
| Exception stack | ❌ | ❌ | ✅ |
| Export debug bundle | ❌ | ❌ | ✅ |

### 2.4 Stepper（步驟指示器）

在工作台模式頂列顯示 6 步精簡 stepper：

```
[①來源] → [②拆頁] → [③ISO] → [④判讀] → [⑤命名] → [⑥更名]
  ready    ready     ready    running    idle      idle
```

每步狀態：`idle` / `running` / `ready` / `warn` / `blocked`
點擊已完成的步可跳到對應的調校 Tab。

---

## 3. Pilot List / Diagnostic Plan

### 3.1 Pilot Item Schema

每個 pilot item：

```typescript
interface PilotItem {
  id: string;                    // e.g. "P01"
  stage: string;                 // "input" | "parse" | "detect" | "naming" | "apply"
  name: string;                  // 人類可讀名稱
  purpose: string;               // 目的（一句話）
  requiredInputs: string[];     // 需要哪些輸入
  successCondition: string;     // 成功條件
  warnCondition: string;        // warn 條件
  blockedCondition: string;     // blocked 條件
  status: "idle" | "running" | "ready" | "warn" | "blocked" | "skipped";
  userSummary: string;          // 顯示給一般使用者的文字
  engineerDetail: string;       // 顯示給工程師的詳細診斷
  autoFixActions: string[];     // 可自動修復的動作
  manualFixActions: string[];   // 需要人工調整的動作
  detail?: Record<string, unknown>; // 任意診斷資料
}
```

### 3.2 完整 Pilot List（18 項）

#### P01 — Input Discovery
- **目的**：確認有可用的輸入來源（工作資料夾、combine PDF 或 page folder）
- **需要輸入**：work_folder 或 combine_pdf 或 page_folder
- **成功條件**：至少找到一個有效 PDF 來源
- **warn 條件**：找到多個可能的 combine PDF，自動選了評分最高的
- **blocked 條件**：沒有任何 PDF 來源
- **使用者摘要**：「找到 PDF 來源：piping.pdf（18 頁）」
- **工程師診斷**：列出所有候選 combine PDF 及其評分，顯示選擇原因
- **自動修復**：無（需使用者確認來源）
- **人工調整**：手動選擇 combine PDF 或 page folder

#### P02 — PDF Source Check
- **目的**：確認 PDF 檔案可讀且頁數正確
- **需要輸入**：combine_pdf
- **成功條件**：pypdf 可讀取，page count > 0
- **warn 條件**：page count > 500（可能效能問題）
- **blocked 條件**：檔案不存在、無法讀取、page count = 0
- **使用者摘要**：「PDF 可讀，共 18 頁」
- **工程師診斷**：檔案路徑、檔案大小、page count、PDF version、是否加密
- **自動修復**：無
- **人工調整**：檢查 PDF 是否損壞、是否被其他程式鎖定

#### P03 — Page Split Check
- **目的**：確認拆頁結果正確（頁數對、檔名正確）
- **需要輸入**：combine_pdf, page_folder（或自動拆頁）
- **成功條件**：拆出 page_count 個 PDF，每個可讀
- **warn 條件**：部分頁面拆出但檔名模式不符預期
- **blocked 條件**：拆頁失敗、拆出 0 個 PDF
- **使用者摘要**：「已拆成 18 個單頁 PDF」
- **工程師診斷**：列出每個頁面 PDF 路徑、大小、頁數
- **自動修復**：若 page_folder 不存在，自動執行 split_pdf_to_pages
- **人工調整**：手動補齊缺失頁面

#### P04 — ISO List Parse Check
- **目的**：確認 ISO list 檔案可讀
- **需要輸入**：iso_list
- **成功條件**：成功讀取 .xlsx/.xlsm/.csv，有 header row 和 data rows
- **warn 條件**：檢測到多個可能的 ISO list，自動選了評分最高的；或 encoding fallback（cp950/big5）
- **blocked 條件**：找不到 ISO list、檔案損壞、無 data rows
- **使用者摘要**：「ISO List 已載入：iso_list.xlsx」
- **工程師診斷**：檔案路徑、encoding、sheet count、header row index、data row count、候選檔案評分
- **自動修復**：自動探索附近 ISO list 候選、自動選最佳 sheet
- **人工調整**：手動選擇 ISO list 檔案、手動選擇 sheet

#### P05 — Sheet / Column Mapping Check
- **目的**：確認 sheet 選擇和欄位對應正確
- **需要輸入**：iso_list, sheet_name, serial_col, line_col
- **成功條件**：找到流水號欄位和圖號/檔名欄位，有有效 data rows
- **warn 條件**：欄位是自動猜測的（非手動指定）、部分 rows 的 serial 或 line_no 為空
- **blocked 條件**：找不到流水號欄位或圖號/檔名欄位
- **使用者摘要**：「ISO 欄位：流水號=欄A，圖號=欄D，共 64 筆」
- **工程師診斷**：所有 headers、猜測分數、serial_col 和 line_col 的前 8 筆樣本值
- **自動修復**：`guess_iso_columns()` 自動猜測
- **人工調整**：手動選擇 serial_col / line_col、手動選擇 sheet

#### P06 — Serial Number Detection
- **目的**：對每頁 PDF 執行流水號 OCR 判讀
- **需要輸入**：page PDFs, serial_region, confidence_threshold
- **成功條件**：所有頁面判讀完成，信心值 >= threshold
- **warn 條件**：部分頁面信心值 < threshold（會 fallback 到頁序）
- **blocked 條件**：所有頁面判讀失敗
- **使用者摘要**：「流水號判讀完成，16/18 頁信心充足」
- **工程師診斷**：每頁的 vision result（text/confidence/message）、使用的 ROI、是否觸發 fallback
- **自動修復**：二階段自動校準（`calibrate_serial_region_from_qimage`）、ISO list 校正（`correct_result_with_iso_lookup`）
- **人工調整**：調整 ROI、調整 confidence threshold、手動輸入流水號

#### P07 — Drawing Number Detection
- **目的**：對每頁 PDF 執行圖號 OCR 判讀（如啟用）
- **需要輸入**：page PDFs, drawing_region
- **成功條件**：所有頁面判讀完成
- **warn 條件**：部分頁面判讀失敗
- **blocked 條件**：N/A（圖號通常從 ISO list 來，非 OCR）
- **使用者摘要**：「圖號從 ISO List 取得」
- **工程師診斷**：每頁的 drawing vision result
- **自動修復**：無（圖號主要靠 ISO list）
- **人工調整**：手動輸入圖號

#### P08 — ROI Confidence
- **目的**：評估整體 ROI 設定品質
- **需要輸入**：所有 page 的 vision results
- **成功條件**：平均 confidence > 0.85
- **warn 條件**：平均 confidence 0.70-0.85，或有 > 20% 頁面低於 threshold
- **blocked 條件**：平均 confidence < 0.50
- **使用者摘要**：「OCR 信心：良好（平均 0.91）」
- **工程師診斷**：每頁 confidence 分佈、低信心頁面列表、建議調整方向
- **自動修復**：無
- **人工調整**：調整 ROI、使用多頁採樣校準、提高 render 解析度

#### P09 — Duplicate Detection
- **目的**：偵測重複流水號
- **需要輸入**：所有 page 的 serial
- **成功條件**：沒有重複流水號
- **warn 條件**：有重複流水號但來自不同判讀值（可能是 OCR 誤判）
- **blocked 條件**：有相同流水號指向不同圖號
- **使用者摘要**：「無重複流水號」
- **工程師診斷**：列出所有重複的 serial、對應的 page、判讀信心、可能的修復
- **自動修復**：無
- **人工調整**：手動修正流水號、重新判讀特定頁面

#### P10 — Missing Serial Detection
- **目的**：偵測 ISO list 中未對應到任何頁面的流水號
- **需要輸入**：ISO records, detected serials
- **成功條件**：ISO list 中所有流水號都有對應頁面
- **warn 條件**：有 ISO records 未被對應（可能頁面缺失）
- **blocked 條件**：超過 30% ISO records 未對應
- **使用者摘要**：「ISO List 64 筆全數對應」
- **工程師診斷**：列出未對應的 ISO records、可能的 serial mismatch
- **自動修復**：無
- **人工調整**：檢查是否有缺頁、檢查流水號判讀是否錯誤

#### P11 — Naming Pattern Validation
- **目的**：確認 naming pattern 合法且可產生有效檔名
- **需要輸入**：pattern
- **成功條件**：pattern 包含 {serial} 和 {line}，產生的檔名不含非法字元
- **warn 條件**：pattern 使用非預設值、部分檔名過長（> 200 chars）
- **blocked 條件**：pattern 缺少 {serial} 或 {line}、產生的檔名含非法字元
- **使用者摘要**：「命名格式：{serial}--{line}.pdf」
- **工程師診斷**：pattern 解析結果、非法字元清單
- **自動修復**：無
- **人工調整**：編輯 pattern

#### P12 — Rename Draft Generation
- **目的**：產生完整命名草稿
- **需要輸入**：page PDFs, ISO records, pattern, vision results
- **成功條件**：所有頁面產出新檔名
- **warn 條件**：部分列狀態為 warn（低信心、無對應 ISO record 等）
- **blocked 條件**：部分列狀態為 blocked（重複目標、目標已存在、無效檔名）
- **使用者摘要**：「產生 18 筆命名草稿：14 ready, 2 warn, 2 blocked」
- **工程師診斷**：每列的 status、note、confidence、vision_message
- **自動修復**：無（需人工審查 warn/blocked 列）
- **人工調整**：編輯流水號、編輯圖號、編輯新檔名、標記已複核

#### P13 — Blocked Rows Explanation
- **目的**：對每個 blocked 列提供詳細原因和修復建議
- **需要輸入**：blocked rows
- **成功條件**：每個 blocked 列有明確的原因和至少一個修復建議
- **warn 條件**：N/A
- **blocked 條件**：N/A（這是診斷項目）
- **使用者摘要**：「2 筆阻擋：1 筆目標重複、1 筆目標已存在」
- **工程師診斷**：每列的 blocked reason、conflicting paths、建議動作
- **自動修復**：無
- **人工調整**：修改衝突的 serial/line_no、選擇覆蓋或跳過

#### P14 — Manual Correction Path
- **目的**：提供人工修正的完整路徑
- **需要輸入**：所有 warn/blocked rows
- **成功條件**：所有 warn/blocked 列有明確的修正步驟
- **warn 條件**：N/A
- **blocked 條件**：N/A
- **使用者摘要**：「2 筆需手動修正，請開啟工作台處理」
- **工程師診斷**：每列的修正路徑（改流水號 → 重判 → 確認）、可一鍵批次處理的項目
- **自動修復**：無
- **人工調整**：逐列或批次修正

#### P15 — Apply / Dry-Run / Rollback Path
- **目的**：確保更名操作安全可回復
- **需要輸入**：selected rows, rename operations
- **成功條件**：所有 selected rows 的 target 路徑合法、不衝突
- **warn 條件**：部分 target 已存在（需確認覆蓋）
- **blocked 條件**：有非法檔名、有跨磁碟 move、有檔案被鎖定
- **使用者摘要**：「12 筆待更名，dry-run 通過」
- **工程師診斷**：完整 rename plan、每筆的 source→target、衝突檢測結果
- **自動修復**：dry-run 驗證
- **人工調整**：確認 dry-run、執行 apply、必要時 rollback

#### P16 — Export Log / Report Path
- **目的**：匯出完整診斷報告
- **需要輸入**：run_id, plan, pilot results
- **成功條件**：成功匯出 CSV + JSON run log
- **warn 條件**：部分診斷資料不完整
- **blocked 條件**：無法寫入匯出路徑
- **使用者摘要**：「已匯出診斷報告」
- **工程師診斷**：匯出路徑、檔案大小、包含的項目
- **自動修復**：自動選擇匯出路徑
- **人工調整**：選擇匯出路徑

#### P17 — Profile Save/Load Check
- **目的**：確認 profile 讀寫正常
- **需要輸入**：profile_folder
- **成功條件**：profile 成功載入或儲存
- **warn 條件**：使用預設 profile（無自訂設定）
- **blocked 條件**：state store 不可寫
- **使用者摘要**：「已載入此資料夾的設定」
- **工程師診斷**：profile 完整內容（ROI、pattern、ISO 路徑、欄位）、儲存時間
- **自動修復**：自動從工作資料夾載入 profile
- **人工調整**：編輯 profile 內容、另存新 profile

#### P18 — Windows File Lock Check
- **目的**：確認沒有 PDF 被其他程式鎖定
- **需要輸入**：page PDFs
- **成功條件**：所有 PDF 可讀寫
- **warn 條件**：部分 PDF 被唯讀開啟
- **blocked 條件**：部分 PDF 被獨佔鎖定（無法更名）
- **使用者摘要**：「檔案未被鎖定」
- **工程師診斷**：列出被鎖定的檔案、鎖定程序
- **自動修復**：無（需手動關閉鎖定程序）
- **人工調整**：關閉 Adobe Acrobat / Explorer preview、重試

---

## 4. Error Log / Run Log 設計

### 4.1 Run Log Schema（JSON）

```typescript
interface IsoRunLog {
  schema_version: 2;
  run_id: string;                    // uuid
  run_type: "autopilot" | "workbench" | "engineer";
  created_at: string;                // ISO 8601
  updated_at: string;

  // 輸入
  inputs: {
    work_folder: string;
    combine_pdf: string;
    page_folder: string;
    iso_list: string;
    sheet_name: string | null;
    serial_col: number | null;
    line_col: number | null;
    pattern: string;
    detect_serials: boolean;
  };

  // Profile
  profile: {
    folder: string | null;
    exists: boolean;
    serial_region: { left: number; top: number; width: number; height: number };
    drawing_region: { left: number; top: number; width: number; height: number };
    confidence_threshold: number;
  };

  // 階段結果
  stages: {
    source_discovery: StageResult;
    pdf_split: StageResult;
    iso_parse: StageResult;
    serial_detection: StageResult;
    naming_draft: StageResult;
    apply: StageResult;
  };

  // 命名草稿（最終狀態）
  rows: IsoPlanRow[];

  // 摘要
  summary: {
    total: number;
    ready: number;
    warn: number;
    blocked: number;
    selected: number;
    applied: number;
  };

  // Pilot 結果
  pilot_results: PilotItem[];

  // 失敗資訊（如果失敗）
  failure: {
    failed_stage: string;            // 哪個階段失敗
    error_type: string;              // exception class name
    error_message: string;           // user-facing
    exception_stack: string;         // developer detail
    traceback_lines: string[];      // 完整 traceback
  } | null;

  // 使用者摘要
  user_summary: string;              // 一到兩句話

  // 建議下一步
  suggested_actions: {
    action: string;                  // "open_workbench" | "adjust_roi" | "edit_serial" | "retry" | "export_bundle"
    label: string;                   // 按鈕文字
    target_tab?: string;            // 調校模式 tab
    params?: Record<string, unknown>;
  }[];

  // Replay
  replay: {
    command: string;                 // e.g. "python -m launcher.app.tauri_iso_workflow"
    payload: IsoWorkflowRequest;    // 可直接 replay 的完整 request
    note: string;                    // replay 注意事項
  };

  // Debug bundle
  export_paths: {
    run_log_json: string;
    plan_csv: string;
  };
}

interface StageResult {
  status: "idle" | "running" | "ready" | "warn" | "blocked" | "failed";
  started_at: string | null;
  finished_at: string | null;
  message: string;                   // user-facing
  detail: Record<string, unknown>;   // developer detail
  issues: IsoWorkflowIssue[];
}
```

### 4.2 Run Log 儲存位置

```
.runtime/
  iso_runs/
    {run_id}/
      run.json         ← 完整 Run Log（上述 schema）
      plan.csv         ← 命名草稿 CSV（可選）
      debug_bundle.zip ← 匯出的診斷包（可選）
```

### 4.3 一鍵失敗時的 Run Log 產生

一鍵 pipeline 在**任何階段失敗**時，自動：
1. 產生 run_id
2. 記錄到目前為止的所有 stage result
3. 記錄 exception stack
4. 寫入 `.runtime/iso_runs/{run_id}/run.json`
5. 顯示失敗對話框（見第 7 節）

---

## 5. ROI / 調校設計

### 5.1 ROI 區域定義

```python
@dataclass(frozen=True)
class SerialVisionRegion:
    left: float = 0.62    # 相對於頁寬的比例 (0.0–0.95)
    top: float = 0.0
    width: float = 0.38
    height: float = 0.24
```

現有預設值：
- **流水號 ROI**：`(0.62, 0.00, 0.38, 0.24)` — 右上角
- **圖號 ROI**：`(0.50, 0.66, 0.50, 0.34)` — 右下角

### 5.2 ROI 調校 UI（在調校模式 > ROI 校準 Tab）

```
┌ ROI 校準 ──────────────────────────────────────────────────┐
│ [流水號 ROI] [圖號 ROI]                                     │
│                                                             │
│ ┌ 整頁 PDF 預覽（含 overlay）──────────────────────────┐   │
│ │                                                       │   │
│ │    ┌─────────────────┐                                │   │
│ │    │ 流水號區域       │  ← 藍色半透明框，可拖曳/縮放    │   │
│ │    │ 判讀: 003 (0.94) │                                │   │
│ │    └─────────────────┘                                │   │
│ │                                                       │   │
│ │              ┌─────────────────────┐                  │   │
│ │              │ 圖號區域             │ ← 綠色半透明框     │   │
│ │              │ 判讀: AB-123 (0.88) │                  │   │
│ │              └─────────────────────┘                  │   │
│ └───────────────────────────────────────────────────────┘   │
│                                                             │
│ 流水號 ROI: left [======62%=====]  0.62                     │
│             top  [===0%========]  0.00                      │
│             width[=====38%======]  0.38                     │
│             height[====24%======]  0.24                     │
│                                                             │
│ [多頁採樣: 第 1 頁 ▼]  [自動校準] [重設預設] [儲存 profile]  │
│                                                             │
│ ┌ Confidence Heatmap ──────────────────────────────────┐   │
│ │ 頁1 ■ 頁2 ■ 頁3 ■ 頁4 □ 頁5 ■ 頁6 ■ ...              │   │
│ │ ■ >0.85  □ 0.70-0.85  ▨ 0.50-0.70  ▯ <0.50         │   │
│ └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 功能清單

| 功能 | 說明 | 實現方式 |
|------|------|---------|
| **拖框調整** | 在 PDF overlay 上直接拖曳 ROI 框 | React + CSS transform，把座標轉成比例傳給後端 |
| **四向 slider** | left/top/width/height 獨立調整 | 四個 range input，範圍 0.00–1.00，step 0.01 |
| **即時重判** | 調整 ROI 後自動重判目前頁 | debounce 500ms 後呼叫 `preview_iso_pdf_page` |
| **Overlay preview** | PDF 預覽上疊加 ROI 框 | Canvas 或絕對定位 div，顏色：流水號=藍、圖號=綠 |
| **多頁採樣** | 下拉選頁，看不同頁的 ROI 效果 | 前端維護 page list，切換時重新 preview |
| **Confidence heatmap** | 所有頁面的信心值一條 bar | 色彩編碼的 grid，點擊可跳到該頁預覽 |
| **自動校準** | 用 RapidOCR 找「流水號」文字，自動擴展 ROI | 後端 `calibrate_serial_region_from_qimage` 已有 |
| **重設預設** | 回復到 `DEFAULT_SERIAL_REGION` / `DEFAULT_DRAWING_REGION` | 一鍵重置 |
| **儲存 profile** | 把目前 ROI 存入 per-folder profile | `save_iso_naming_profile(store, folder, profile)` |
| **回復上版設定** | 從 state store history 回復 | profile 儲存時保留上一版在 `profile.prev` |

### 5.4 Profile 設計

```python
@dataclass(frozen=True)
class IsoNamingProfile:
    serial_region: SerialVisionRegion   # 流水號 ROI
    drawing_region: SerialVisionRegion  # 圖號 ROI
    confidence_threshold: float         # OCR 信心門檻
    pattern: str                        # 命名格式
    iso_list_path: Path | None          # ISO list 路徑
    sheet_name: str | None              # sheet 名稱
    serial_col: int | None              # 流水號欄位 index
    line_col: int | None                # 圖號欄位 index
```

**Profile 儲存策略**：
- Per-folder：每個工作資料夾一個 profile，存於 `AppStateStore.iso_naming_profile(folder)`
- 預設值：`DEFAULT_SERIAL_REGION` / `DEFAULT_DRAWING_REGION` 是出廠設定
- 載入順序：`DESKTOP_SUPPORT_PROJECT_ROOT` env → profile_folder → page_folder → work_folder
- 調校不污染預設：profile 儲存時寫到工作資料夾的 key，不會改全區預設
- 回復：profile 儲存時保留前一版 (`prev_profile`)，可一鍵回復

---

## 6. 工作台狀態機

### 6.1 完整狀態定義

```
                    ┌──────────┐
                    │ waiting   │ 初始：無任何輸入
                    └────┬─────┘
                         │ discover_sources()
                         ▼
                    ┌──────────┐
                    │input_ready│ 來源已選定、可開始
                    └────┬─────┘
                         │ build_plan()
                         ▼
              ┌─────────────────┐
              │ draft_generating │ pipeline 執行中
              └────────┬────────┘
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
      ┌─────────┐ ┌────────┐ ┌──────────┐
      │draft_   │ │ warn    │ │ blocked   │
      │ready    │ │(有黃燈) │ │(有紅燈)   │
      └────┬────┘ └───┬────┘ └────┬─────┘
           │          │           │
           │          │ 人工修正   │ 人工修正
           │          ▼           ▼
           │     ┌─────────┐ ┌──────────┐
           │     │ manual  │ │ manual   │
           │     │ review  │ │ review   │
           │     └────┬────┘ └────┬─────┘
           │          │           │
           │     ┌────┴───────────┘
           │     ▼
           │ ┌──────────────┐
           │ │ ready_to_apply│ 所有選取列可更名
           │ └──────┬───────┘
           │        │ apply()
           │        ▼
           │  ┌──────────┐
           │  │ applying │
           │  └────┬─────┘
           │       │
           │  ┌────┴─────┐
           │  ▼          ▼
           │┌────────┐┌────────┐
           ││applied ││ failed │
           │└────────┘└────┬───┘
           │               │
           │          ┌────┴─────┐
           │          ▼          ▼
           │     ┌─────────┐┌──────────┐
           │     │replaying││ tuning   │ (從 run log 還原)
           │     └─────────┘└──────────┘
           │
           └──── 所有狀態可回到 waiting（清除全部）
```

### 6.2 每個狀態的 UI 行為

#### waiting
- **顯示**：空白頁或來源選擇提示
- **可按**：選工作資料夾、選 combine PDF、選 page folder、選 ISO list
- **禁用**：產生草稿、套用、匯出
- **下一步**：來源齊全後自動進入 `input_ready`

#### input_ready
- **顯示**：來源摘要 chip、checklist（全部 ready）、主按鈕「開始一鍵命名」
- **可按**：「開始一鍵命名」、修改來源、載入/儲存 profile
- **禁用**：套用、匯出
- **下一步**：按主按鈕 → `draft_generating`

#### draft_generating
- **顯示**：進度條（若批次判讀）、stepper 目前階段亮起、主按鈕顯示進度百分比
- **可按**：取消（若支援串流）
- **禁用**：所有修改、套用、匯出
- **下一步**：完成後依結果進入 `draft_ready` / `warn` / `blocked`

#### draft_ready（全綠）
- **顯示**：命名表、摘要「14 ready」、主按鈕「套用 14 筆更名」（綠色）
- **可按**：套用、匯出 CSV、逐列編輯、PDF 預覽
- **禁用**：無
- **下一步**：按套用 → `applying`

#### warn（有黃燈，無紅燈）
- **顯示**：命名表（warn 列黃底）、摘要「12 ready, 2 warn」、主按鈕「仍要套用（黃燈 2）」（黃色）
- **可按**：勾選「我已確認黃燈」→ 主按鈕變「套用 14 筆」、逐列確認、編輯修正、匯出 CSV
- **禁用**：主按鈕（未勾確認前）
- **下一步**：勾選確認後按套用 → `applying`；或修正 warn → `draft_ready`

#### blocked（有紅燈）
- **顯示**：命名表（blocked 列紅底）、摘要「10 ready, 2 warn, 2 blocked」、主按鈕「先修復 2 個阻擋項」（紅色，disabled）
- **可按**：跳轉到第一個 blocked 列、編輯修正、匯出 CSV、開啟調校模式
- **禁用**：主按鈕（有 blocked 時完全禁用套用）
- **下一步**：修正 blocked → `warn` 或 `draft_ready`

#### manual_review
- **顯示**：命名表（focus 在問題列）、PDF 校對面板、逐列動作按鈕
- **可按**：「確認此列」「下一問題」「採用判讀值」「跳過」
- **禁用**：套用（需回到 ready_to_apply）
- **下一步**：所有 warn/blocked 處理完 → `ready_to_apply`

#### ready_to_apply
- **顯示**：命名表（selected 列勾選）、dry-run 摘要、主按鈕「套用 N 筆更名」
- **可按**：套用、dry-run 預覽、匯出 CSV
- **禁用**：無
- **下一步**：按套用 → `applying`

#### applying
- **顯示**：進度「正在更名... 5/14」
- **可按**：無（不可取消）
- **禁用**：全部
- **下一步**：完成 → `applied`；失敗 → `failed`

#### applied
- **顯示**：結果摘要「已更名 14 個 PDF」、結果清單
- **可按**：匯出 CSV、返回 waiting（新作業）、查看 run log
- **禁用**：套用（已完成）
- **下一步**：新作業 → `waiting`

#### failed
- **顯示**：失敗訊息、失敗階段、exception summary
- **可按**：「開啟調校模式」「匯出問題包」「重試」
- **禁用**：套用
- **下一步**：調校 → `tuning`；重試 → `input_ready`

#### replaying
- **顯示**：從 run log 載入的完整現場（來源、profile、plan、pilot results）
- **可按**：所有工作台/調校操作
- **禁用**：無
- **下一步**：修正完 → 重新產生 draft

#### tuning
- **顯示**：調校模式 6 個 Tab
- **可按**：所有調校操作
- **禁用**：無
- **下一步**：返回工作台 → `manual_review` 或重新產生 draft

---

## 7. 一鍵失敗後的導流

### 7.1 一般使用者看到的失敗畫面

```
┌ 一鍵命名失敗 ──────────────────────────────────────┐
│                                                     │
│  ⚠️ 命名草稿產生時遇到問題                           │
│                                                     │
│  在「流水號判讀」階段失敗：                           │
│  部分頁面 OCR 信心過低，無法自動判定                  │
│                                                     │
│  ┌ 摘要 ────────────────────────────────────────┐   │
│  │ 已處理: 16 頁    ready: 14    warn: 2         │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  [📋 複製問題摘要]  適合傳給工程師                    │
│  [📦 匯出問題包]     包含 log + 截圖 + 設定           │
│  [🔧 開啟工作台]     逐列修正問題（需要經驗）          │
│  [↩ 返回]            放棄此次作業                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 7.2 「複製問題摘要」產生的文字

```
ISO 命名失敗摘要
─────────────────
Run ID: a1b2c3d4
時間: 2026-06-08 14:30
資料夾: D:\Projects\F3-Piping
PDF: piping.pdf (18 pages)
ISO List: iso_list.xlsx (64 rows)
失敗階段: 流水號判讀
原因: 2 頁 OCR 信心低於 0.70
Warn 頁面: page 5 (0.52), page 12 (0.48)
建議: 調整流水號 ROI 或手動輸入
```

### 7.3 「匯出問題包」內容

```
debug_bundle_{run_id}.zip
├── run.json           ← 完整 Run Log
├── plan.csv           ← 命名草稿
├── profile.json       ← 使用的 profile
├── screenshots/        ← 低信心頁面的預覽截圖（可選）
│   ├── page_05.png
│   └── page_12.png
└── README.txt         ← 給工程師的說明
```

### 7.4 工程師開啟工作台後的現場還原

1. 從 run log 讀取 `inputs` → 自動填入來源路徑
2. 從 run log 讀取 `profile` → 自動套用 ROI/pattern/columns
3. 從 run log 讀取 `rows` → 重建命名表
4. 從 run log 讀取 `pilot_results` → 顯示各階段狀態
5. 自動跳到第一個 warn/blocked 列
6. 底部 event log 顯示完整執行歷程

---

## 8. 測試策略

### 8.1 測試矩陣

| # | 測試 | 類型 | 環境 | 優先級 |
|---|------|------|------|--------|
| T01 | 一鍵 happy path（combine PDF → split → ISO → detect → apply） | integration | Python + PyQt6 offscreen | P0 |
| T02 | 一鍵失敗但產生 run log（ISO list 缺欄位） | integration | Python | P0 |
| T03 | 工作台讀取 run log 還原現場 | integration | Python | P0 |
| T04 | ROI 調整後重新產生 draft | integration | Python + PyQt6 | P0 |
| T05 | blocked rows manual correction（編輯 serial 解 blocked） | integration | Python | P0 |
| T06 | dry-run apply（驗證不實際更名） | unit | Python | P0 |
| T07 | apply + rollback（更名後回復） | integration | Python | P0 |
| T08 | profile save/load（寫入後重讀一致） | unit | Python | P1 |
| T09 | malformed ISO list（空檔案、缺 header） | unit | Python | P1 |
| T10 | missing pages（combine PDF 只有 2 頁但 ISO list 64 筆） | unit | Python | P1 |
| T11 | duplicate serial（多頁 OCR 判出相同流水號） | unit | Python | P1 |
| T12 | OCR confidence low（全部低於 threshold） | unit | Python | P1 |
| T13 | path contains Chinese characters（路徑含中文/日文） | unit | Python + Windows | P1 |
| T14 | Windows file locked（PDF 被 Adobe 開啟） | integration | Windows | P1 |
| T15 | Tauri browser fallback（Vite dev server 可啟動 ISO 頁面） | smoke | Node.js | P2 |
| T16 | Tauri native（完整 ISO workflow 在 Tauri window） | e2e | Tauri + VS 工具鏈 | P2 |
| T17 | ISO list encoding（UTF-8 BOM / cp950 / big5） | unit | Python | P2 |
| T18 | Pilot list 18 項全部通過 | unit | Python | P2 |
| T19 | Run log JSON schema 驗證 | unit | Python | P2 |
| T20 | Export debug bundle（含所有必要檔案） | integration | Python | P2 |

### 8.2 測試輔助工具

- **sample fixtures**：準備 3 頁的 sample combine PDF + sample ISO list (.xlsx + .csv)
- **mock OCR**：`conftest.py` 中提供 mock `SerialVisionResult` 的 fixture
- **臨時目錄**：所有測試使用 `tempfile.TemporaryDirectory`，不污染實際檔案

---

## 9. 建議模組/檔案結構

```
launcher/
├── plugins/iso_tools/          # 核心邏輯（現有，穩定）
│   ├── iso_naming.py           # ISO 命名核心
│   ├── serial_vision.py        # OCR / 影像判讀
│   ├── serial_correction.py    # ISO list 校正
│   ├── profile.py              # Profile dataclass + load/save
│   ├── validator.py            # Checklist 驗證
│   ├── rename_plan.py          # 更名計畫
│   ├── issues.py               # 問題模型
│   └── run_log.py              # [新增] Run Log schema + read/write
│
├── app/
│   ├── tauri_iso_workflow.py   # ISO workflow bridge（擴充）
│   ├── tauri_iso_preview.py    # PDF preview bridge（擴充）
│   ├── tauri_iso_worker.py     # Batch detect worker（現有）
│   └── tauri_iso_engineer.py   # [新增] 調校模式專用 bridge（pilot list, debug bundle）
│
├── ui/                         # PyQt6 legacy（保留，不做大改）
│   └── iso_pdf_naming_dialog.py
│
frontend/tauri-spike/src/
├── isoWorkflow.ts              # API layer（現有，擴充）
├── components/
│   └── iso/
│       ├── IsoAutopilot.tsx           # [重構] 一鍵頁
│       ├── IsoWorkbench.tsx           # [重構] 工作台
│       ├── IsoEngineer.tsx            # [新增] 調校模式（6 tabs）
│       ├── IsoSourcePanel.tsx         # [新增] 來源設定面板（可收合）
│       ├── IsoNamingTable.tsx         # [新增] 命名表
│       ├── IsoPdfInspector.tsx        # [新增] PDF 校對面板（含 ROI overlay）
│       ├── IsoRoiCalibration.tsx      # [新增] ROI 拖框校準
│       ├── IsoChecklist.tsx           # [新增] Checklist 燈號
│       ├── IsoPilotList.tsx           # [新增] Pilot list（調校模式）
│       ├── IsoRunLogViewer.tsx        # [新增] Run log 檢視器
│       ├── IsoResultDialog.tsx        # [新增] 一鍵結果頁
│       ├── IsoFailedDialog.tsx        # [新增] 一鍵失敗對話框
│       ├── IsoStepper.tsx             # [新增] 步驟指示器
│       ├── IsoEventLog.tsx            # [新增] 底部事件 log
│       └── IsoProfileEditor.tsx       # [新增] Profile 編輯器
│
├── hooks/
│   ├── useIsoPlan.ts           # [新增] plan state machine hook
│   ├── useIsoProfile.ts        # [新增] profile load/save hook
│   ├── useIsoPreview.ts        # [新增] PDF preview + cache hook
│   └── useIsoPilot.ts          # [新增] pilot list 狀態 hook
│
tests/
├── test_iso_run_log.py         # [新增] Run log 讀寫測試
├── test_iso_pilot_list.py      # [新增] Pilot list 驗證測試
├── test_iso_profile.py         # 現有
├── test_iso_naming.py          # 現有
└── fixtures/
    ├── sample_combine_3page.pdf # [新增] 3 頁 sample PDF
    ├── sample_iso_list.xlsx     # [新增] sample ISO list
    └── sample_iso_list.csv      # [新增] sample ISO list CSV

docs/
├── iso_pdf_workbench_blueprint_v0.2.md  # 本文件
├── ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md
└── iso_pdf_workbench_next_stage_v0.1.md
```

---

## 10. 優先級

### 現在就該做（架構地基，不做後面會一直返工）

| # | 項目 | 範圍 | 預計工時 |
|---|------|------|---------|
| **0a** | **Profile 持久化** — 前端接上 `load_iso_profile` / `save_iso_profile`，重開後設定還在 | 前端 + bridge（後端已支援） | 0.5d |
| **0b** | **Run Log schema 定義 + 實作** — `run_log.py` + `IsoRunLog` dataclass + 讀寫函數 | 純 Python | 1d |
| **0c** | **一鍵失敗時自動產生 run log** — 在 `tauri_iso_workflow.py` 的 exception handler 寫 run log | Python bridge | 0.5d |
| **0d** | **階段 0 的 bridge 細指令化** — 確保後端 12 個 action 都獨立可用（現已大部分可用） | 確認即可 | 0.5d |

### 一鍵更穩後做（直接提升日常可用度）

| # | 項目 | 範圍 | 預計工時 |
|---|------|------|---------|
| **1a** | **ROI 拖框校準 UI** — React 版 `IsoRoiCalibration` + 前端把 region 傳進 preview | 前端 + bridge（後端已支援） | 2d |
| **1b** | **更名前 dry-run 計畫對話框** — 舊版 `RenamePlanDialog` 邏輯搬成 React | 前端 | 1d |
| **1c** | **CSV 匯出** — `export_plan_csv` 前端呼叫（後端已支援） | 前端 | 0.5d |
| **1d** | **一鍵失敗對話框** — `IsoFailedDialog`（含複製摘要、匯出問題包、開啟工作台） | 前端 | 1d |
| **1e** | **底部事件 log** — `IsoEventLog`，從 issues 串流顯示 | 前端 | 0.5d |

### 工作台大改版時做（功能 parity、可取代舊版）

| # | 項目 | 範圍 |
|---|------|------|
| **2a** | **工作台版面重構** — 設定軌(可收合) + 命名表 + PDF 校對放大 | 前端 |
| **2b** | **逐列複核閉環** — 採用判讀值、確認此列、下一個問題 | 前端 + bridge |
| **2c** | **調校模式 6 Tab** — 來源診斷 / ISO 對映 / ROI 校準 / 命名規則 / Pilot List / Run Log | 前端 |
| **2d** | **Pilot List 完整實作** — 18 項 pilot items + 即時狀態更新 | 前端 + Python |
| **2e** | **批次判讀進度條 + 取消** — 需要串流後端（worker_host 常駐） | 前端 + Python worker |
| **2f** | **Confidence heatmap** — ROI 校準 Tab 內的多頁信心視覺化 | 前端 |
| **2g** | **Replay from run log** — 讀取 run log → 還原現場 → 重跑 | 前端 + bridge |
| **2h** | **一鍵結果頁** — 指標卡 + 問題縮影 + 後續動作 | 前端 |
| **2i** | **標記舊版 PyQt dialog 為 deprecated** | 標記即可 |

### 等要正式包 exe 前做

| # | 項目 | 範圍 |
|---|------|------|
| **3a** | **移除舊版橋接按鈕**（當 2a–2i 完成後） | 前端 + 可選刪除 legacy dialog |
| **3b** | **Undo log（SQLite）** | Python（新功能） |
| **3c** | **衝突自動 `_v2` 後綴** | Python |
| **3d** | **欄位下拉附樣本值** | 前端 + Python |
| **3e** | **Tauri native e2e 測試** | CI (windows-latest) |

---

## 附錄 A：既存設計約束（不建議改變）

1. **後端判斷邏輯保持 Python 單一真相源**。不在 React 重刻 `_row_status`、`_serial_for_row`、`correct_result_with_iso_lookup` 等核心邏輯。
2. **PyQt6 保留**作為 legacy 對照路線，不做大改，只標 deprecated。
3. **一鍵 pipeline 的輸入自動發現**（`_auto_combine_pdf_candidate`、`_nearby_iso_list_candidates`）已是成熟邏輯，不建議變更。
4. **ISO list 欄位自動猜測**（`guess_iso_columns`）同樣保持現狀。
5. **命名草稿的 ready/warn/blocked 分類規則**（`_row_status`）保持現狀，只在工作台提供手動覆寫。

## 附錄 B：與既有文件的關係

- `ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md`：提供 parity checklist（45 項盤點），本文件的優先級直接對應其 P0/P1/P2 分類。
- `iso_pdf_workbench_next_stage_v0.1.md`：提供 Autopilot/Workbench 產品分層與 UI 版面圖，本文件的 §2 資訊架構沿用其設計方向。
- `iso_pdf_workbench_audit.md`：提供 UX/OCR 痛點分析，本文件不重複其內容。
