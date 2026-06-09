# ISO PDF 命名工作台 — 下一階段優化提案 v0.1

> 對接文件：`docs/iso_pdf_workbench_audit.md`（UX/OCR 痛點）、`docs/ui_uplift_proposal_v0.1.md`（設計 token）
> 對接代碼：`launcher/ui/iso_pdf_naming_dialog.py`（2585 行，god dialog）、`launcher/plugins/iso_tools/`（pipeline 元件）、`launcher/workers/worker_host.py`（subprocess host）
> 寫作角度：**這是每天會被工程師＋主管反覆使用的 Windows 工具，重點是「降低出錯機率、降低決策疲勞、可重複」**。
> 不重複 audit 已寫過的 UX 問題；本文聚焦：一鍵頁 / Checklist 狀態機 / Autopilot pipeline / 工程師模式 / 安全機制 / 架構重構 / 實作路線。

---

## 0. TL;DR

1. **產品分層**：把命名工作台拆成兩個入口模式 — **Autopilot（一鍵頁）給長官、Workbench（進階）給工程師**。共用同一個 Job 物件、同一條 pipeline，差別在 UI 與「停下來問」的策略。
2. **狀態機落地**：抽 `IsoAutoPilot` orchestrator，把現在散在 dialog 內的 `_load_*` / `_run_*` / `_apply_*` 改成 12 個明確 state + 事件流。
3. **Checklist 即守門員**：紅黃綠不是裝飾，是「能不能按下一鍵套用更名」的硬閘。每一條 check 都有 fix action。
4. **安全機制三件套**：Rename Plan dry-run + Undo log（SQLite） + 防覆蓋策略表。任何一項缺一，主按鈕鎖死。
5. **god dialog 拆解**：2585 行 dialog 按「Autopilot / Workbench / SourcePanel / ProblemTable / PreviewPanel / EngineerMode」六塊切，pipeline 全部 QThread 化，事件用 signal。

---

## 1. 產品設計建議

### 1.1 兩種使用者，兩種模式，一個 Job

| 維度 | Autopilot（一鍵頁） | Workbench（進階工作台） |
| --- | --- | --- |
| 對象 | 長官 / 一般工程師 / 重複作業 | 調校者 / 收到新圖框格式時 |
| 預設停下來時機 | 紅燈、衝突、確認列 | 每一頁都可介入 |
| 主畫面 | 左 30% 來源 + 右 40% Checklist + 下 30% 主按鈕區 | 現有 dialog 重排版 |
| 對 OCR 失敗的態度 | 「降為人工複核佇列」而非中斷 | 「立刻顯示在問題列」 |
| Profile | 自動載入「最近使用」 | 顯示 profile 編輯器 |
| 不准做的事 | 改 ROI / 改命名格式 / 改 ISO 欄位 | 無 |

> **關鍵**：兩個模式吃的是同一個 `IsoNamingJob` dataclass，差別只是 UI 觀感與 pause point。不要為了 Autopilot 又寫一套 pipeline。

### 1.2 Landing / 結果頁要不要

**要**。Autopilot 完成（或部分完成）後一定要有一頁 Result：

- 上方：成功 N、警告 M、阻擋 K，三大數字。
- 中間：問題列縮影（最多 10 列，超過 → 跳 Workbench）。
- 下方四顆按鈕：`匯出 CSV` / `撤銷此次更名` / `跳到 Workbench 修` / `完成（回 Autopilot 首頁）`。
- 結果頁的 batch_id 寫進 Undo log，可由 launcher 入口的 `最近作業` 直接回到此頁。

### 1.3 「最近作業」側欄

長官常常會問「上禮拜那批是不是這個流程跑的？」。在 Autopilot 首頁右下角放一個 `最近 5 筆作業` 清單（從 Undo log 讀），點進去看 Result 頁。一頁簡單但極大量被使用。

### 1.4 主按鈕設計（一顆按鈕承載多種語意）

主按鈕**單一**，標籤與顏色跟著狀態走，避免 21 顆按鈕的災難：

| 狀態 | 標籤 | 色 | 行為 |
| --- | --- | --- | --- |
| Idle / 來源未齊 | `選擇來源 PDF` | muted | disabled |
| 來源齊但未起飛 | `開始一鍵命名` | accent | 啟動 pipeline |
| Pipeline 跑中 | `處理中… (45%)` | accent + progress | disabled，可點旁邊小 X 取消 |
| Pipeline 完成全綠 | `套用更名（12 筆）` | success | 跳 rename plan dialog |
| 有黃燈 | `仍要套用（黃燈 3）` | warning | 需勾「我已確認黃燈」才亮 |
| 有紅燈 | `先修復 2 個阻擋項` | danger | 點下跳到第一個紅燈的修復頁 |
| 完成 | `查看結果` | neutral | 跳 Result 頁 |

---

## 2. UI 版面建議

### 2.1 Autopilot 一鍵頁版面（推薦尺寸 1280×760）

```
┌──────────────────────────────────────────────────────────────┐
│ Header: 專案 [台塑F-3]   Profile [F3-Vendor-A v3]  [工程師模式↗]│
├─────────────────────┬────────────────────────────────────────┤
│ 來源設定 (30%)      │ 起飛前 Checklist (40%)                 │
│ ─────────────────── │ ───────────────────────────────────── │
│ 📄 合併 PDF         │ 🟢 PDF 可讀 ( 18 頁 )                  │
│   [拖放或選擇]      │ 🟢 ISO List sheet=Sheet1 列=64         │
│   ✓ piping.pdf      │ 🟢 Profile 已套用 (F3-Vendor-A v3)     │
│                     │ 🟡 OCR 信心 < 0.6 的頁: 2              │
│ 📊 ISO List          │   → 仍可繼續，會列入問題列            │
│   [選擇 / 自動找]    │ 🔴 目標檔已存在: 3 個                  │
│   ✓ iso_list.xlsx   │   → [自動加 _v2] [覆蓋] [改命名格式]   │
│                     │                                        │
│ 📁 輸出資料夾        │ 落地前 Checklist                       │
│   [預設：旁邊]       │ ⚪ 問題列已審核 0/5                    │
│   ✓ ./output         │ ⚪ rename plan dry-run 未跑            │
│                     │ ⚪ undo 檔位準備就緒                   │
├─────────────────────┴────────────────────────────────────────┤
│ Recent: F3-0518 / F3-0517 / NEC-0515  │  ⓘ 操作說明  ⚙ 進階   │
├──────────────────────────────────────────────────────────────┤
│      ████████████████  開始一鍵命名  ████████████████          │
│      （ESC 取消 · Ctrl+E 工程師模式 · F1 說明）                │
└──────────────────────────────────────────────────────────────┘
```

關鍵：
- **三欄不是 splitter**，是固定比例。Autopilot 不准被使用者拉壞。
- 左欄三個區塊每個都有 `自動偵測` 按鈕（從工具列當前路徑、`%USERPROFILE%/Downloads` 與 launcher 最近紀錄抓）。
- 右欄 Checklist 每一條 collapse / expand，紅燈預設展開帶修復按鈕。
- 主按鈕固定佔下方 ~80px 高，整列點擊區，符合 Fitts's law。
- 進階入口在右上角而非主畫面中央，避免長官誤觸。

### 2.2 Result 頁版面

```
┌──────────────────────────────────────────────────────────────┐
│ Result · F3-0521-1432 · 套用於 14:33                          │
├──────────────────────────────────────────────────────────────┤
│       ✅ 12 成功    ⚠ 3 警告    ⛔ 0 阻擋                       │
├──────────────────────────────────────────────────────────────┤
│ 問題列縮影 (3)                                                │
│  P05  W001 OCR 信心 0.42  已人工確認 → 1037--ISO-P05.pdf      │
│  P11  W002 ISO 無此流水號 已標記 unknown                       │
│  P14  W004 多筆 ISO 匹配 1042 已選擇第 2 筆                    │
├──────────────────────────────────────────────────────────────┤
│ [匯出 CSV] [撤銷此次更名] [跳到 Workbench] [完成 → 首頁]       │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Workbench（進階）

維持現有 dialog 的功能，但按 `docs/iso_pdf_workbench_audit.md` 1.1/1.2 節提的方向：
- 左控制欄按鈕縮為 5 顆（其餘隱進 `⋯ 更多`）。
- 中間「命名表」與右邊「預覽」改成上下不等高的 split，預覽至少 360 px 高。
- 加 step indicator：`① 來源 → ② 拆頁 → ③ ISO → ④ 判讀 → ⑤ 命名 → ⑥ 更名`。

---

## 3. 一鍵流程狀態機

### 3.1 States

```
IDLE
  └─ on(source_set) → SCANNING

SCANNING                # 偵測 PDF/ISO/Profile，跑 preflight checks
  ├─ on(red)   → BLOCKED_PREFLIGHT
  ├─ on(green) → READY
  └─ on(cancel)→ IDLE

READY                   # 主按鈕點亮
  └─ on(start) → SPLITTING

SPLITTING               # pypdf 拆頁 → temp dir
  ├─ on(done)  → OCR_QUEUEING
  └─ on(error) → FAILED

OCR_QUEUEING            # 把每頁丟進 QThreadPool
  └─ on(any_page_done) → OCR_RUNNING (持續直到全部完成或被取消)

OCR_RUNNING
  ├─ on(all_done) → MATCHING
  ├─ on(cancel)   → ABORTED
  └─ on(error)    → FAILED

MATCHING                # 流水號 ↔ ISO List 配對
  └─ on(done)    → PLANNING

PLANNING                # 生成 rename plan，跑 validator
  ├─ on(red)     → BLOCKED_LANDING
  ├─ on(yellow)  → AWAITING_REVIEW
  └─ on(green)   → AWAITING_CONFIRM

AWAITING_REVIEW         # 有黃燈，使用者必須勾「已審核」才能進 confirm
  └─ on(reviewed_all) → AWAITING_CONFIRM

AWAITING_CONFIRM        # 顯示 rename plan dialog
  ├─ on(confirm) → RENAMING
  └─ on(cancel)  → PLANNING (或回 Workbench)

RENAMING                # 真實 OS 更名 + 寫 undo log
  ├─ on(done)  → DONE
  └─ on(error) → PARTIAL_FAILED  (已寫的部分能撤銷)

DONE / FAILED / ABORTED / PARTIAL_FAILED → 進 Result 頁
```

### 3.2 狀態轉換守則

- **每個狀態都可以 cancel → ABORTED**（除了 RENAMING，RENAMING 為原子批次）。
- **任何 ERROR 都會記錄完整 traceback 到 audit log**（`./logs/iso_audit.jsonl`）。
- **狀態變更只能透過 `IsoAutoPilot.transition(event)`**，UI 不准直接 setText / setEnabled。

### 3.3 一鍵繼續策略矩陣（紅燈時誰能放行）

| 情境 | Autopilot 是否允許繼續 | Workbench 是否允許繼續 |
| --- | --- | --- |
| 全綠 | ✅ 自動繼續 | ✅ |
| 黃燈：OCR 信心低 | ❌ 必須勾「已審核」 | ✅ |
| 黃燈：ISO 無此流水號 | ❌ 必須選「mark unknown」或「加入 ISO List」 | ✅ |
| 紅燈：命名衝突 | ❌ 鎖死 | ❌ 鎖死 |
| 紅燈：目標檔已存在 | ❌ 必須選策略（_v2/覆蓋/跳過） | ❌ 必須選策略 |
| 紅燈：違法字元 | ✅ 自動 sanitize（log 警告） | ✅ 自動 sanitize |
| 紅燈：來源檔被鎖 | ❌ 提示關閉檔案 | ❌ |

---

## 4. Checklist 項目表

> 三段：起飛前 (Preflight) / 處理中 (Inflight) / 落地前 (Landing)
> 每條 check 都有 `id` / `level` / `name` / `auto_fix` / `manual_fix_hint`，用 dataclass 落實。

### 4.1 起飛前 (Preflight)

| ID | 名稱 | 紅黃綠定義 | Auto fix | Manual hint |
| --- | --- | --- | --- | --- |
| PF01 | 合併 PDF 存在 / 可讀 | 不存在=紅；可讀=綠 | 從 launcher 當前 cwd / Downloads 自動找 | 重新選擇 |
| PF02 | PDF 頁數 > 0 | 0=紅；>=1=綠 | — | 確認檔案完整 |
| PF03 | ISO List 存在 | 不存在=紅 | 自動找同層 `iso_list*.xlsx` | 重新選擇 |
| PF04 | ISO List sheet 可讀 | header 找不到=紅 | 試 Sheet1/0/最寬 sheet | 進工程師模式對映 |
| PF05 | Profile 已選 | 無 profile=黃（用預設） | 套用「最近使用」 | 選 profile |
| PF06 | 輸出資料夾可寫 | 不可寫=紅 | 建立子資料夾 | 改路徑 |
| PF07 | OCR engine 可用 | RapidOCR import 失敗=紅 | — | 重新安裝 |
| PF08 | 沒有同名 Job 正在跑 | 有=紅 | — | 等舊 Job 完成 |
| PF09 | ROI 設定齊全（流水號+圖號） | 缺=黃 | 套 profile 預設 | 進 Workbench 設 |
| PF10 | Profile 版本相符 | 不符=黃 | — | 升級 profile |

### 4.2 處理中 (Inflight)

| ID | 指標 | 顯示方式 |
| --- | --- | --- |
| IF01 | 拆頁進度 | progress bar + N/M |
| IF02 | OCR 進度 | progress bar + N/M + 取消 |
| IF03 | OCR 完成率 < 95% | 不阻擋，落地前轉黃 |
| IF04 | 平均信心 | 數字 + 顏色 |
| IF05 | ISO 配對率 | N/M |

### 4.3 落地前 (Landing)

| ID | 名稱 | 紅黃綠定義 | 解除條件 |
| --- | --- | --- | --- |
| LD01 | 問題列審核完成 | 有未審核=紅 | 全部標 reviewed |
| LD02 | rename plan dry-run 通過 | 任一筆 dry-run fail=紅 | 重跑通過 |
| LD03 | 無重複目標檔名 | 有=紅 | 改命名格式或人工改 |
| LD04 | 無違法字元 | 有=自動 sanitize=黃 | 自動處理後綠 |
| LD05 | 目標檔已存在策略已選 | 未選=紅 | 選 skip/_v2/overwrite |
| LD06 | 來源檔未被其他程式鎖定 | 鎖定=紅 | 關閉 PDF |
| LD07 | undo log 可寫入 | 寫不進=紅 | 改路徑 |
| LD08 | Windows 路徑長度 < 250 | 超出=紅 | 縮命名或啟用長路徑 |

---

## 5. 錯誤 / 警告分類表

```python
# launcher/plugins/iso_tools/issues.py（建議新增）
@dataclass(frozen=True)
class IssueCode:
    code: str          # E001 / W001 / I001
    level: str         # "red" / "yellow" / "info"
    name: str
    where: str         # preflight / ocr / matching / planning / landing
    blocks_apply: bool
    auto_fix: str | None
```

| Code | Level | 名稱 | 觸發階段 | 是否阻擋更名 | 預設修復 |
| --- | --- | --- | --- | --- | --- |
| E001 | red | 來源 PDF 不存在 | preflight | ✅ | 重新指定 |
| E002 | red | ISO List 讀取失敗 | preflight | ✅ | 進工程師模式對映 |
| E003 | red | 目標檔已存在（未選策略） | planning | ✅ | 跳「衝突策略」對話框 |
| E004 | red | 命名衝突（兩列同檔名） | planning | ✅ | 自動加流水號後綴 |
| E005 | red | 流水號衝突（兩頁判讀同號） | matching | ✅ | 進問題列人工指定 |
| E006 | red | 來源檔被鎖 | landing | ✅ | 提示關閉檔案 |
| E007 | red | 路徑超長 | landing | ✅ | 縮命名格式 |
| E008 | red | undo log 無法寫入 | landing | ✅ | 改 undo dir |
| W001 | yellow | OCR 信心 < threshold | ocr | ⚠ 需審核 | 人工確認或重 OCR |
| W002 | yellow | ISO List 無此流水號 | matching | ⚠ 需審核 | mark unknown / 加入 ISO |
| W003 | yellow | 圖號欄位空白 | matching | ⚠ 需審核 | 從圖框 OCR / 手動 |
| W004 | yellow | 多筆 ISO 匹配同流水號 | matching | ⚠ 需審核 | 人工選列 |
| W005 | yellow | OCR 與 CV 結果不一致 | ocr | ⚠ 需審核 | 採 ISO 校正結果 |
| W006 | yellow | 違法字元已 sanitize | planning | ❌ | 自動處理（log） |
| W007 | yellow | 目標檔已存在（已自動加 _v2） | planning | ❌ | 自動處理（log） |
| I001 | info | OCR 已人工校正 | post-review | ❌ | — |
| I002 | info | 使用了預設 profile | preflight | ❌ | — |
| I003 | info | 自動找到 ISO List | preflight | ❌ | — |

**視覺規則**：
- 表格列底色：red=`#fde2e2`、yellow=`#fff4d6`、info=`#eaf3fb`、ok=透明。
- 狀態欄獨立成兩個 column：`level` icon + `code`，可排序、可篩選。
- 「只看問題列」= filter `level in {red, yellow}`。

---

## 6. 工程師調校模式建議

### 6.1 入口

- 右上角單一按鈕 `⚙ 工程師模式`，按下後切到 `EngineerModeDialog`（不取代 Autopilot 主視窗，另開）。
- 可選：用 `engineering_mode_pin` 設定一個 4 碼 PIN，避免長官誤觸。寫在 `~/.iso_workbench/settings.json`。

### 6.2 內容（六個 tab）

| Tab | 功能 | 對應檔 |
| --- | --- | --- |
| ROI | 流水號 / 圖號 / 自訂 ROI；多圖框（per-vendor） | `plugins/iso_tools/profile.py` 加 `roi_set: dict[str, ROIRect]` |
| OCR | engine 選擇（rapidocr/tesseract）、信心 threshold、預處理 pipeline（gray/threshold/sharpen toggle）、template matching 開關 | `plugins/iso_tools/serial_vision.py` 抽 config |
| ISO 映射 | sheet 名 / header row / 欄位對應 / 排除列 | `plugins/iso_tools/iso_naming.py` SERIAL_HEADERS / DRAWING_NAME_HEADERS / LINE_HEADERS 改成 profile-driven |
| 命名格式 | template 編輯（`{serial}--{drawing}.pdf`）+ 變數白名單 + 即時預覽（用第一頁判讀結果） | 新增 `plugins/iso_tools/name_template.py` |
| Profile | 儲存 / 載入 / 匯入 / 匯出 / diff；profile 帶 `schema_version` | 擴充 `profile.py` 加版本化 |
| 進階 | log level / undo 保留天數 / dry-run 預設 / 多執行緒數量上限 / RapidOCR cache 路徑 | `launcher/core/settings.py` |

### 6.3 Profile JSON schema（建議）

```json
{
  "schema_version": 2,
  "id": "F3-Vendor-A",
  "name": "F3 Vendor A 圖框",
  "vendor": "Vendor A",
  "drawing_frame_hash": "sha1:...",  // 用於自動偵測圖框
  "roi": {
    "serial": {"x": 0.94, "y": 0.02, "w": 0.06, "h": 0.06},
    "drawing_no": {"x": 0.78, "y": 0.92, "w": 0.20, "h": 0.06}
  },
  "ocr": {
    "engine": "rapidocr",
    "confidence_threshold": 0.6,
    "preprocess": ["gray", "adaptive_threshold"]
  },
  "iso_mapping": {
    "sheet": "Sheet1",
    "header_row": 1,
    "columns": {
      "serial": ["流水號", "序號"],
      "drawing_no": ["圖號", "drawing no"],
      "line_no": ["管線號碼", "line no"]
    }
  },
  "naming": {
    "template": "{serial}--{drawing_no}.pdf",
    "sanitize": "replace_with_underscore",
    "on_conflict": "append_v"
  }
}
```

> 重要：`schema_version` 與 `drawing_frame_hash` 是兩條救命線。前者讓你日後升級不炸舊 profile；後者讓 Autopilot 看到 PDF 自動推薦 profile。

### 6.4 多 Profile / 多圖框自動切換

Autopilot 拿到 PDF 後，**對第一頁圖框做 perceptual hash**（imagehash 套件即可），跟所有 profile 的 `drawing_frame_hash` 算距離，距離夠近 → 自動套用；不夠近 → 黃燈提示「請選 profile」。

---

## 7. 問題列審核 UI 簡化

### 7.1 主表收斂

把現在 8 欄縮到 6 欄，狀態獨立成 icon + code：

| 欄 | 寬 | 內容 |
| --- | --- | --- |
| ☐ | 24 | 選取列（批次操作） |
| Page | 50 | P01 |
| Level | 40 | 🔴/🟡/🟢 icon |
| Issue | 80 | E003 / W001 / — |
| Source | 自動 | 原檔名 |
| Target | 自動 | 預定新檔名 |

「判讀信心」、「圖號」、「管線號」這些 → 移到右側 detail pane（點列出現），表格本身不再塞長字串。

### 7.2 「只看問題列」 = filter，不重畫表

現在 `_refresh_statuses` 整張重畫，是性能瓶頸。改 `QSortFilterProxyModel` + custom filter，O(N) 變 O(log N)。

### 7.3 右側 detail pane

選列後右側顯示：
- 上：頁面 thumbnail（current code 已有，沿用）
- 中：流水號 ROI 局部放大 + OCR 候選清單 + `[採用]` 按鈕
- 下：圖號 ROI 局部放大 + ISO List 候選列 + `[採用]` 按鈕
- 右下角：`標為已審核`（解黃燈用）/ `跳過此頁`（不更名）

### 7.4 「忘記修就套用」如何防

- 主按鈕的 enable 邏輯只看 Checklist：LD01 未解 → 永遠不亮。
- 黃燈未審核時，主按鈕標籤是 `仍要套用（黃燈 3）`+ 需要勾「我已知悉並接受」checkbox 才解鎖。每次更名後 checkbox 自動歸零（避免變成肌肉記憶亂按）。

---

## 8. 安全機制建議

### 8.1 Rename Plan 三段式

1. **Build**：planner 生成 `RenamePlan(items: list[RenameItem])`，每筆有 `src / dst / action / reason / risk`。
2. **Dry-run**：對每一筆做 `os.path.exists(dst)`、字元檢查、長度檢查、鎖定檢查。所有 fail 寫進 `risk`。
3. **Apply**：原子批次 — 全部成功才算成功，中途失敗 → rollback 已改名的部分。

### 8.2 Undo log（SQLite）

```sql
CREATE TABLE rename_batch (
  batch_id TEXT PRIMARY KEY,    -- F3-0521-1432
  applied_at TEXT,
  job_json TEXT,                -- 完整 IsoNamingJob snapshot
  status TEXT                   -- applied / rolled_back / partial
);
CREATE TABLE rename_item (
  batch_id TEXT,
  src_abs TEXT,
  dst_abs TEXT,
  applied INT,
  rolled_back INT
);
```

存 `~/.iso_workbench/undo.sqlite`。一鍵 rollback：依 `rename_item` 反向 rename。

### 8.3 CSV 匯出

- `rename_plan_<batch>.csv`：套用前匯出（給長官審核或留存）。
- `rename_result_<batch>.csv`：套用後匯出（含 status）。
- 欄位：`page, src_basename, dst_basename, action, status, level, issue_code, drawing_no, line_no, ocr_confidence`。

### 8.4 防覆蓋策略

`on_conflict`（profile 設定 + 對話框可臨時改）：
- `skip`：跳過該筆，紀錄 W007。
- `append_v`：附 `_v2`、`_v3`…（往上掃直到不存在）。
- `append_timestamp`：附 `_20260521_143312`。
- `overwrite`：需勾「我知道我在做什麼」才出現。

### 8.5 違法字元 sanitize

Windows 不允許 `< > : " / \ | ? *`，建議 sanitize 規則寫進 profile（預設全部轉 `_`）。**sanitize 後仍要記 W006**，避免「悄悄」改掉檔名。

### 8.6 路徑長度

預設 250 字元上限（留邊際），超過 → LD08 紅燈。建議在 settings 加 `enable_long_path: bool`，啟用後檢查升到 32760。

### 8.7 檔案鎖定

Windows 下用 `msvcrt.locking` 或試開 `O_RDWR` 判斷。鎖定中 → 提示「請關閉 Acrobat / Edge / 瀏覽器分頁」並列出可能的程序名（用 `psutil` 掃）。

### 8.8 Audit log

`./logs/iso_audit.jsonl`，每行一個事件：
```json
{"ts":"2026-05-21T14:33:12+08:00","batch":"F3-0521-1432","event":"rename_applied","src":"...","dst":"...","by":"lizonghong084@gmail.com"}
```

---

## 9. 架構重構建議

### 9.1 現況問題

- `iso_pdf_naming_dialog.py` 2585 行：UI + 流程 + OCR 呼叫 + 表格 + preview + 部分 IO 全混在一起。
- pipeline 元件（`iso_naming.py` / `serial_vision.py` / `profile.py` / `rename_plan.py` / `serial_correction.py`）已經拆出來，但 dialog 內仍有自寫的 `_load_*` / `_run_*` 邏輯，與 plugins 重複。
- 沒有狀態機，沒有事件流。每個按鈕直接呼叫 method，加新 state 就要在 N 個 method 裡改 `setEnabled`。
- OCR 在主 thread 跑（`_update_region_preview(detect=True)`）。批次判讀用 `QApplication.setOverrideCursor + blockSignals` 整段卡 UI。
- `worker_host.py` 有 subprocess 機制但目前主要服務 launcher 的 action，沒被命名工作台使用。

### 9.2 建議目錄

```
launcher/
├── plugins/iso_tools/                # 純邏輯，不依賴 PyQt
│   ├── core/
│   │   ├── job.py                    # IsoNamingJob, IsoNamingResult dataclass
│   │   ├── pipeline.py               # IsoAutoPilot orchestrator
│   │   ├── state_machine.py          # 12 個 state + transition
│   │   ├── events.py                 # 事件型別
│   │   ├── pdf_split.py
│   │   ├── ocr.py                    # OCR 引擎抽象（包 serial_vision）
│   │   ├── iso_index.py              # ISO List loader / index（包 iso_naming）
│   │   ├── matcher.py                # 流水號 ↔ ISO 配對 + serial_correction
│   │   ├── name_builder.py           # template 化命名
│   │   ├── planner.py                # rename plan + dry-run
│   │   ├── executor.py               # rename + undo + sanitize
│   │   ├── validator.py              # 產生 IssueCode
│   │   ├── profile.py                # profile + schema 版本化
│   │   └── issues.py                 # IssueCode 定義
│   ├── plugin.json
│   └── actions.json
├── ui/iso_pdf/
│   ├── autopilot_page.py             # ← 新；一鍵頁
│   ├── checklist_panel.py            # ← 新
│   ├── source_panel.py               # ← 新
│   ├── result_page.py                # ← 新
│   ├── workbench_dialog.py           # ← 由 iso_pdf_naming_dialog.py 拆
│   ├── problem_table.py              # ← 由 dialog 拆
│   ├── preview_panel.py              # ← 由 dialog 拆
│   ├── engineer_mode/
│   │   ├── dialog.py
│   │   ├── tab_roi.py
│   │   ├── tab_ocr.py
│   │   ├── tab_iso.py
│   │   ├── tab_naming.py
│   │   ├── tab_profile.py
│   │   └── tab_advanced.py
│   ├── widgets/
│   │   ├── traffic_light.py
│   │   ├── main_action_button.py
│   │   └── step_indicator.py
│   ├── batch_detect.py               # 既有
│   ├── region_selector.py            # 既有
│   └── styles.py                     # 既有
└── workers/
    ├── worker_host.py                # 既有
    └── iso_runner.py                 # ← 新；IsoAutoPilot 的 QThread 包裝
```

### 9.3 PyQt6 Threading 規則

- `IsoAutoPilot.run()` **不准在主 thread**。包成 `QObject + QThread`，事件用 `pyqtSignal` 回拋。
- OCR per-page 用 `QThreadPool + QRunnable`，限制最大並行（profile.advanced.max_parallel，預設 4，避免 RapidOCR 把 CPU 燒爆）。
- 預覽渲染（`QPdfDocument.render`）放 `QThreadPool` 而非主 thread，並設 LRU cache（最近 8 頁）。
- 表格更新：pipeline 累積一段（200 ms 或 16 列）才 emit 一次 `rows_changed`，避免 itemChanged 風暴。

### 9.4 launcher 重量控制

- `launcher/plugins/iso_tools/__init__.py` 維持薄薄一層，**不要 `import` 任何 pyqt / pdf / cv2**。
- `launcher/ui/iso_pdf/__init__.py` 同上。
- 真正 import 重量級套件（RapidOCR / opencv / pypdf）放到 `core/ocr.py` / `core/pdf_split.py`，且**用 lazy import**：
  ```python
  def get_ocr():
      from rapidocr_onnxruntime import RapidOCR  # noqa
      ...
  ```
- launcher 啟動只 `import launcher.plugins.iso_tools`（讀 plugin.json），實際 dialog 在使用者按下「ISO 命名」才 import。
- 用 `python -X importtime` 量一次 launcher 冷啟，記在 audit 文件。

### 9.5 god dialog 拆解優先順序

1. 把 `_apply_rename` / `_build_rename_plan` 抽到 `core/planner.py` + `core/executor.py`（先抽底層，UI 不動）。
2. 把 OCR 相關 `_detect_*` 抽到 `core/ocr.py`，dialog 改呼叫 `IsoAutoPilot`。
3. 把表格相關 `_refresh_*` 抽 `ui/iso_pdf/problem_table.py`，並改 `QAbstractTableModel`。
4. 把預覽抽 `ui/iso_pdf/preview_panel.py`。
5. 最後再蓋 `autopilot_page.py`。

---

## 10. 實作優先順序

> 以「一週 = 工程師可投入 8–10 小時」為節奏。每階段最後都要可 demo。

### Sprint 1（本週 / P0 - 主幹搭起來）

1. **Day 1–2**：抽 `core/planner.py` + `core/executor.py`，把現有 `rename_plan.py` 與 dialog 內的 apply 邏輯合併；加 dry-run 與 undo log（SQLite）。
2. **Day 3**：抽 `core/issues.py` + `core/validator.py`，定義 E001~E008 / W001~W007 / I001~I003，**全表收斂**。
3. **Day 4–5**：抽 `core/pipeline.py` + `core/state_machine.py`，把現有 dialog 內流程串成事件驅動。
4. **Day 6**：寫 unit test：planner / executor / validator 三件。

### Sprint 2（下週 / P1 - 一鍵頁）

5. `widgets/traffic_light.py`、`widgets/main_action_button.py`、`widgets/step_indicator.py`。
6. `ui/iso_pdf/autopilot_page.py` 三欄版面骨架，吃 `IsoAutoPilot` 事件。
7. `ui/iso_pdf/checklist_panel.py`，把 LD01-LD08、PF01-PF10 接上 validator。
8. `ui/iso_pdf/source_panel.py`（自動偵測 + 拖放）。
9. 把工具列「ISO 命名」入口改成 → Autopilot；舊 dialog 改名 Workbench，從右上「進階」進入。

### Sprint 3（P2 - 工程師模式 + 安全機制完整化）

10. `engineer_mode/` 六個 tab。
11. Profile schema v2 + `drawing_frame_hash` 自動推薦。
12. 結果頁 + 最近作業側欄。
13. CSV 匯出（套用前 + 套用後）。
14. Audit log JSONL。
15. 檔案鎖定偵測（psutil）。

### Sprint 4（P3 - 性能與重構收尾）

16. OCR 全面 QThreadPool 化。
17. 表格改 `QAbstractTableModel + QSortFilterProxyModel`。
18. 預覽渲染 LRU cache。
19. launcher lazy import、`python -X importtime` 基準。
20. 拆完後 `iso_pdf_naming_dialog.py` 應該 < 600 行。

---

## 11. 可以直接交給 Codex 的分階段任務清單

> 規格：每個任務都標 `輸入檔` / `輸出檔` / `驗收標準`，給 Codex 才不會幻覺。

### Phase 1 — 抽 Pipeline 核心（純邏輯，無 UI 改動）

**T1.1 建立 issue 與 validator**
- 新檔：`launcher/plugins/iso_tools/core/issues.py`、`launcher/plugins/iso_tools/core/validator.py`。
- 內容：`IssueCode` dataclass、E001-E008 / W001-W007 / I001-I003 全表常數、`Validator.validate_preflight(job)` / `validate_planning(plan)` / `validate_landing(plan)` 三個函式。
- 驗收：`tests/iso_tools/test_validator.py` 至少 12 個 test，全綠。
- 不准動：`iso_pdf_naming_dialog.py`。

**T1.2 抽 planner + executor**
- 新檔：`core/planner.py`、`core/executor.py`、`core/job.py`（`IsoNamingJob` / `RenameItem` / `RenamePlan` dataclass）。
- 既有檔：`plugins/iso_tools/rename_plan.py` 內容整併進 `planner.py`（保留檔名作為 re-export 過渡）。
- 加入：dry-run、SQLite undo log（schema 如 §8.2）、防覆蓋策略（skip / append_v / append_timestamp / overwrite）、sanitize。
- 驗收：`test_planner.py` 涵蓋衝突、覆蓋策略、sanitize；`test_executor.py` 涵蓋 dry-run、apply、rollback。

**T1.3 抽 state machine + pipeline**
- 新檔：`core/state_machine.py`（12 個 state 如 §3.1）、`core/pipeline.py`（`IsoAutoPilot` orchestrator）、`core/events.py`。
- 不依賴 PyQt（用 callback 或 Observer）。
- 驗收：`test_state_machine.py` 涵蓋所有合法轉換 + 至少 6 個非法轉換 raise。

**T1.4 抽 OCR / ISO / matcher / name_builder**
- 移 `serial_vision.py` → `core/ocr.py`（保 re-export）。
- 移 `iso_naming.py` 的 ISO 載入 → `core/iso_index.py`；保留 SERIAL_HEADERS/DRAWING_NAME_HEADERS 但改成 profile-driven。
- 移 `serial_correction.py` → `core/matcher.py`。
- 新檔：`core/name_builder.py` 提供 template 化命名。
- 驗收：所有舊呼叫點（dialog + plugin entry）改成 import 新位置；現有 tests 全綠。

### Phase 2 — 一鍵頁 UI 與 PyQt thread 化

**T2.1 通用 widgets**
- 新檔：`ui/iso_pdf/widgets/traffic_light.py`（紅黃綠燈，size 16/24/32）、`main_action_button.py`（含 7 種狀態 §1.4）、`step_indicator.py`（6 步）。
- 全部吃 `ui_uplift_proposal_v0.1.md` 的 design tokens。

**T2.2 Source / Checklist panel**
- 新檔：`ui/iso_pdf/source_panel.py`、`checklist_panel.py`。
- Source panel：拖放 + 自動偵測 + Profile 下拉。
- Checklist：吃 `Validator` 輸出，列 PF01-PF10 / IF01-IF05 / LD01-LD08，紅燈展開帶修復按鈕。

**T2.3 Autopilot page**
- 新檔：`ui/iso_pdf/autopilot_page.py`，三欄如 §2.1，連接 `IsoAutoPilot` signals。
- 入口：`launcher/plugins/iso_tools/actions.json` 加 `"iso.autopilot"`，主工具列「ISO 命名」改指這個。

**T2.4 Worker thread 化**
- 新檔：`launcher/workers/iso_runner.py`，包 `IsoAutoPilot` 成 `QObject + QThread`，pyqtSignal 拋 `state_changed / progress / issue / done`。
- OCR per-page 改 `QThreadPool`，並行上限取 profile。
- 預覽渲染移出主 thread，加 LRU cache。

**T2.5 Result page**
- 新檔：`ui/iso_pdf/result_page.py`，§2.2 版面；含 CSV 匯出與一鍵 rollback。

### Phase 3 — 工程師模式 + Profile v2

**T3.1 Profile schema v2**
- 改：`plugins/iso_tools/profile.py` 加 `schema_version=2`、`drawing_frame_hash`、`naming.template` 等欄位（§6.3）。
- 寫 migration：v1 → v2。
- 驗收：`test_profile_migration.py`。

**T3.2 Engineer Mode Dialog**
- 新檔：`ui/iso_pdf/engineer_mode/dialog.py` + 六個 tab。
- ROI tab：套用 `region_selector.py`；OCR tab：threshold 即時試跑；naming tab：template 即時預覽（吃第一頁判讀結果）。

**T3.3 自動推薦 profile**
- 改：`core/pipeline.py` Preflight 階段，對第一頁圖框做 perceptual hash，與所有 profile 比對；命中 → 自動套；未命中 → 黃燈。

### Phase 4 — 收尾與性能

**T4.1 god dialog 拆解**
- `iso_pdf_naming_dialog.py` → `workbench_dialog.py` + `problem_table.py` + `preview_panel.py`，目標 < 600 行。

**T4.2 表格 model 化**
- `problem_table.py` 改 `QAbstractTableModel + QSortFilterProxyModel`，「只看問題列」改 filter，停止重畫整表。

**T4.3 lazy import 與啟動量測**
- 改 `launcher/plugins/iso_tools/__init__.py`、`launcher/ui/iso_pdf/__init__.py` 移除所有 heavy import。
- 跑 `python -X importtime -m launcher`，寫進 `docs/iso_pdf_workbench_audit.md` 附錄，作為基準。

**T4.4 Audit log + 鎖檔偵測**
- 新檔：`core/audit.py`，所有 state 變更與 rename 寫 `./logs/iso_audit.jsonl`。
- 鎖檔：`core/executor.py` apply 前對每個 src 做 `_check_locked`（試 O_RDWR + psutil），失敗 → E006。

---

## 附錄 A — 給 Codex 的提示語模板

對每個 T 任務，建議用這個 prompt 模板開：

```
你是 Python + PyQt6 工程師。任務 T<id>：<一句話目標>
背景：閱讀 docs/iso_pdf_workbench_next_stage_v0.1.md 第 <章節>。
範圍：只能改/新增以下檔案：<檔案列表>。
不准動：launcher/ui/iso_pdf_naming_dialog.py（除非任務明說）。
驗收：
  1) <點 1>
  2) <點 2>
  3) tests/iso_tools/test_<x>.py 全綠。
程式風格：type hints、dataclass、from __future__ import annotations、無 print 改用 logging。
完成後輸出：變更清單 + 怎麼跑 test。
```

## 附錄 B — 不建議做的事

- ❌ 不要為 Autopilot 寫第二條 pipeline。一條 pipeline 兩個 UI。
- ❌ 不要把 ROI 拖拉做成 Autopilot 首頁元素。長官不會拖。
- ❌ 不要在主 thread 跑 RapidOCR / opencv 任何一行。
- ❌ 不要用 `time.sleep` 或 `QApplication.processEvents()` 假裝 async。
- ❌ 不要把 undo log 寫成 JSON 平檔。會有並行寫入問題。SQLite 是對的。
- ❌ 不要為了「看起來在工作」加假進度條。每個 state 都要有真實 % 來源。

---

> 接下來建議的下一步：開 T1.1（建立 issue 與 validator）。這是 4–6 小時可完成、且能讓後續 Checklist UI 有真實資料可吃的入口任務。
