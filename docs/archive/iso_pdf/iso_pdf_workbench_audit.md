# ISO PDF 命名工作台 — 深度審查與重構計畫

> 對象範圍:`launcher/ui/iso_pdf_naming_dialog.py`(1629 行)、`launcher/plugins/iso_tools/iso_naming.py`、`launcher/plugins/iso_tools/serial_vision.py`、對應三個 test。
> 對話框體量:`1280×760` 最小、`1440×900` 預設;主檔 1629 行為全專案最大檔。
> 審查角度:**這是 Windows 常駐工具的關鍵子流程,不是要它變漂亮,是要它出錯機率更低、速度更快、可重複**。

---

## 1. 目前命名工作台的主要 UX 問題

### 1.1 排版 — 已經擠到飽和

整個視窗目前分成上中下三層:`Header` / `body 三欄 splitter` / `Terminal`。

- **左側控制面板(390 px,可滾動)** 塞了兩個 GroupBox、**12 顆按鈕**(來源 5 顆 + ISO/命名 7 顆,還沒算 primary)、4 個欄位 label、1 個 pattern 輸入框,加上 `addStretch`。控制面板 `setMaximumWidth(450)`,但因為按鈕都用 `QGridLayout 2 欄`,在某些 DPI 下會自動換行,實際視覺密度比設計高。
- **右側預覽面板(330 px,固定 max=420)** 塞了 **9 顆按鈕** 分成 4 排(`button_row`/`detect_row`/`serial_row`/`review_row`)、兩個資訊 label、RegionSelector(`minHeight=230`)、裁切預覽 QLabel(`minHeight=120`)。在 1080p 螢幕上預覽 PDF 真正可看的高度其實只剩約 250 px。
- **中間命名表(680 px)** 已固定 8 欄,還有 "需確認:XXX" 這種長字串會撐 `狀態` 欄。
- **底部 Terminal** 預設 150 px,使用者只要看一行訊息要往下捲。

**結論**:控制面板 + 預覽面板的按鈕(共 21 顆)是視覺主噪音源,而**真正的工作區(命名表 + PDF 視覺)被擠到 50% 不到的空間**。

### 1.2 操作順序不明顯

目前流程是「左上 → 左中 → 左下 → 中 → 右」,但畫面上沒有任何**步驟編號**或**進度條**告訴使用者「現在做到第幾步」。21 顆按鈕沒有 stepper 概念。新使用者打開會問:

- 我要先按「載入工具列目前來源」嗎?還是「選擇合併 PDF」?
- 拆頁完成了之後要按「重新讀取單頁 PDF」還是「依 ISO List 更新命名」?
- 「自動判讀欄位」「套用欄位」差別?「找附近 ISO List」「選 ISO List」差別?
- 「判讀目前頁」「批次判讀流水號」「填入判讀流水號」「確認此列」四個按鈕很容易誤點。

**主要動作的順序是線性的**(來源 → 拆頁 → ISO list → 命名 → 套用),目前卻被攤平成「並列的功能群」,使用者必須靠記憶導航。

### 1.3 預覽 / 裁切預覽 / 命名表互相干擾

- 在命名表選列 → `itemSelectionChanged` 直接觸發 `_update_preview_from_selection` → `_show_pdf_preview`:**每次都 `shutil.copy2` 到 temp,然後 `QPdfDocument.load`,接著 render 整頁 800×1100 影像,再走 `_render_corner_preview`**;切列頻繁時會卡 200–600 ms。
- 拖動 RegionSelector:`mouseMoveEvent` 不重新判讀(OK),但 `mouseReleaseEvent` 觸發 `regionCommitted` → `_update_region_preview(detect=True)` → 直接同步跑 OCR;**ROI 拖很大時 RapidOCR 會跑 1–3 秒,UI 完全卡住**。
- 「批次判讀流水號」用 `QApplication.setOverrideCursor(WaitCursor)` + `_table.blockSignals(True)`,**完全 UI 阻塞**,5 頁可能 OK,30 頁以上使用者只能等。沒有取消、沒有進度。
- 命名表 `itemChanged` → `_regenerate_names` → 又改表 → 又觸發 `itemChanged`(被 blockSignals 擋住),但 `_refresh_statuses` 每次都重畫整張表,**O(N) 重畫對 50–100 列以上會有感**。

### 1.4 狀態文字不夠工程化

目前狀態欄是純文字 concat:

```python
status = "可更名" / "未變更" / "缺少命名" / "命名重複" / "目標已存在" / "來源不存在"
if review_issue:
    status = f"需確認:{review_issue}" if status in {"可更名", "未變更"} else f"{status} / 需確認"
```

問題:

- 無法**按狀態排序 / 篩選**(它是字串);也不能按「只看錯誤列」分組。
- "判讀信心" 欄也是字串 `"23 / 0.85 低"`,**無法按信心數值排序**。
- 視覺上只有「黃底」一種高亮 — 信心低、ISO List 找不到、命名重複、目標已存在四種**完全不同的問題**通通是同一個顏色,使用者必須讀文字才知道差別。
- 沒有 **可追蹤的事件編號**:Terminal 的 `[影像判讀] 第 N 列 …` 訊息很多,使用者沒辦法快速從表格列跳到 Terminal 對應那一行。

---

## 2. OCR / 流水號判讀流程的技術問題

### 2.1 誤判來源

讀過 `serial_vision.py` 後,主要誤判來自:

| 來源 | 描述 | 目前處置 |
| - | - | - |
| **題栏邊框被當數字** | findContours 找到細長矩形,寬高碰巧落在 `8<w<75, 25<h<90`,fill_ratio>0.15 也過 | 無;靠 template matching score≥0.55 過濾,有時不夠 |
| **粗框右上角的「页碼/圖號」** | 流水號旁邊還有 sheet 編號(例如 "1 of 5")或圖號末段 | 用 `_BLUE_DIGIT_FULL_X_RATIO=0.966` / `_GRAY_DIGIT_FULL_X_RATIO=0.943` 強制只找 ROI 最右側 |
| **OCR 把「流水號:」標籤的『:』讀成數字** | RapidOCR 偶會把全形冒號當 1 | `_pick_rapidocr_serial_candidate` 取 `digits[-1]` 雖然能擋一部分,但 OCR 把「流水號 1037」整段當成一個 box 時 `digits[-1]="1037"`,實際是 "103" + 邊框 1 |
| **OCR 與 OpenCV 不一致** | OCR 讀到 "1037"、CV 讀到 "103" | `_merge_vision_results` 已處理(取 CV、降信心 0.05)+ `_correct_result_with_iso_lookup` 用 ISO List 校正 |
| **數字 8/0、6/0、5/6 容易誤辨** | template matching 受字型粗細影響 | 192 templates(8 字型 × 4 scale × 6 thickness)有幫助但不夠;score=0.55 門檻偏低 |

### 2.2 框線被當數字 — 目前的處理不夠

`_is_digit_candidate` 規則:

```python
return (
    x > roi_width * x_min_ratio    # 強制最右側
    and y < min(roi_height * 0.20, 150)  # 強制最上端
    and 8 < width < 75
    and 25 < height < 90
    and fill_ratio > 0.15
)
```

**漏洞**:

1. **粗框邊框**:寬度可能落在 8–75,高度落在 25–90,`fill_ratio` 為 1.0(實心)— 完全通過。靠 `_classify_digit` 用 template matching 把 score < 0.55 的擋掉,但**邊框的縱橫比往往接近 0 或數字**,有時剛好像 "1" 或 "7"。
2. **`fill_ratio < 某值` 上限沒設**:極粗的字會接近 1.0,但邊框也是 1.0;**應該加 `fill_ratio < 0.85` 把純色塊濾掉**(數字內部會有筆畫間隙)。
3. **沒用 aspect ratio**:數字 1 的縱橫比 ~0.3、其他數字 ~0.5–0.7;邊框可能是 0.1 或 3+。**加 `0.20 < w/h < 1.2`** 可以擋掉長條框線。
4. **沒做 connected component 過濾**:`RETR_EXTERNAL` 雖然只取外輪廓,但邊框內套小數字會被視為外輪廓的子。

### 2.3 信心值策略不合理

- **`SERIAL_AUTO_FILL_CONFIDENCE = 0.70` 是常數**,沒辦法依專案 / 紙張品質 / 解析度調整。同樣的圖在 4× render 信心可能 0.92,在 2× render 可能 0.62。
- **CV 與 OCR 合併後的信心是 max / min / -0.05 規則**,人讀不出「為什麼這列是 0.85?」。應該保留 CV、OCR 各自的原始信心,並在 tooltip 顯示「CV=0.78, OCR=0.94, merged=0.85 (尾段校正)」。
- **「ISO List 校正」會把信心壓到 0.88 上限**(`max(0.0, min(0.88, result.confidence - 0.04))`),但**校正成功其實應該提高信心而不是降低** — 因為這個流水號既被視覺判讀到、又能在 ISO List 找到對應,反而更可信;目前降信心會把它丟進「需要人工確認」清單,反直覺。

### 2.4 二階段判讀(先找「流水號」文字 → 偏移找數字)— 已實作但只用在「校準框」

`_calibrate_region_from_rapidocr_result` 已經會找「流水號」字樣並 expand 出 ROI(`_expanded_label_region`)。

**問題:這個邏輯只在使用者按「自動校準框」時跑,不在 `detect_serial_from_qimage` 主流程內。**

每張圖判讀時應該:

1. **第一階段**:全圖跑一次 RapidOCR,找「流水號」label 的位置 → 算出該頁的真實 ROI(每張圖可能不同)。
2. **第二階段**:在這個 ROI 內跑 OpenCV + 局部 OCR 抓數字。
3. 失敗才回退到 profile 裡的 fixed ROI。

這比現在「全部用同一個 ROI」穩很多,因為不同廠商的標題欄、不同圖紙方向、不同流水號位置都會自動處理。

### 2.5 校準 profile — 完全沒持久化

- `SerialVisionRegion` 是 frozen dataclass,使用者調整完關閉 dialog 就丟失。
- 沒有「儲存目前判讀區為預設」按鈕;`DEFAULT_SERIAL_REGION = SerialVisionRegion()` 是 hardcode。
- 不同專案(不同 ISO list、不同公司圖框)需要不同 ROI,**應該存到 state.json 並用「最近使用過的資料夾」當 key**。

---

## 3. ISO List 讀取與欄位對應改善建議

### 3.1 Sheet name 選擇

目前:

- `list_iso_sheets` 列出所有 sheet。
- `_preferred_sheet_index` 用 `_score_iso_sheet` 評分,**會對每個 sheet 都跑一次完整 `read_iso_table`** — 100 個 sheet × 5000 列的活頁簿會卡死。
- `_score_iso_sheet` 評分項目合理:`dwg/iso/圖號/清單` 關鍵字 + 有 serial / line col + line 欄是 `file_basename` 加分。

**建議**:

1. Sheet preview 改 **lazy**:只算 sheet 名稱關鍵字分,**不要先讀所有 sheet 內容**。讓使用者在 dropdown 選了之後才 `read_iso_table`。
2. 在 dropdown 顯示 sheet 的「列數、欄數、推測命中度」:`ISO List (24 列 × 12 欄,流水號✓ 圖號✓)`。
3. 多 sheet 比對失敗時提示「請手動選 sheet」而不是預設 sheet 0。

### 3.2 欄位自動猜測

`SERIAL_HEADERS`、`DRAWING_NAME_HEADERS`、`LINE_HEADERS` 三組關鍵字 OK,但:

- **沒有用值的特徵**:流水號欄通常是「短整數 1–9999」,圖號欄是「含 -/ 字母的字串」。在 header 猜測失敗時應該回退到值特徵分析。
- **`_first_header_match` 用完全相等(normalized 後)**,沒有 fuzzy 匹配。"流水序" / "Drawing No.(Final)" 都會錯過。

### 3.3 手動 mapping UI 該怎麼做

目前是兩個 QComboBox(`流水號欄` / `圖號/檔名欄`),項目顯示 `{index+1}. {header}`。

**問題**:沒有 sample preview,使用者只能憑欄名猜。如果有兩個欄都叫「No.」就完全選不出來。

**建議**:

把 ISO List & 欄位這個 group 拆成獨立 dialog 或 inline mini-table,讓使用者看到:

```
┌─ ISO List 對應 ─────────────────────────────┐
│ 檔案: project_iso.xlsx                       │
│ Sheet: [ ISO List ▼ ]   (24 列 × 12 欄)      │
│                                              │
│ 第 1 列  第 2 列  ...  第 12 列              │
│ ───────────────────────────────────────────  │
│ 流水號  | 管線編號  | 圖號          | ...    │
│ 101    | L-100   | 1-S11U-AI-00001-001 | … │
│ 102    | L-200   | 1-S11U-AI-00002-001 | … │
│                                              │
│ 流水號欄: [▼ 1.流水號  101,102,103]          │
│ 圖號欄:   [▼ 3.圖號    1-S11U-...,]          │
│                                              │
│ [自動判讀] [套用]                            │
└──────────────────────────────────────────────┘
```

ComboBox 的 items 把「該欄前 3 個非空值」附在標籤後面,使用者一眼能驗證是不是選對欄。

### 3.4 讀取成功/失敗的視覺提示

目前 `_iso_label` 是一個文字 label:`"ISO list:C:\...\iso.xlsx,Sheet=ISO List,24 筆"`。失敗時用 `QMessageBox.warning` modal — 太重。

**建議**:把 `_iso_label` 改成有狀態顏色的 chip:

- 載入中:灰色 + 進度指示
- 成功:綠色 + ✓ + 「24 筆已套用 / 流水號=A欄 / 圖號=C欄」
- 失敗:紅色 + ✗ + 失敗原因(可點開展開詳細)
- 已選但欄位未套用:橙色 + ⚠

---

## 4. 命名表改善建議

### 4.1 固定顯示 vs 摺疊

**固定顯示(預設)**:`套用`、`old name`、`page`、`new name`、`狀態`(這 5 欄是工作必看)。

**摺疊(預設隱藏,點 header gear 可開)**:`sort/流水號`、`圖號/檔名`、`判讀信心`。

理由:`流水號` 和 `圖號/檔名` 在 ISO List 套用後已經反映到 `new name`,平常只需要看 new name;只在「需要修正」時才開出這兩欄。`判讀信心` 也只在驗證階段需要。

### 4.2 問題列高亮 — 多色化

目前所有需確認列都用同一個 `#fff2b8` 黃。建議依問題類型上色:

| 問題類型 | 背景色 | 條件 |
| - | - | - |
| 信心太低 | `#fff2b8` 黃 | OCR 信心 < threshold |
| ISO List 無此流水號 | `#ffd6d6` 淺紅 | result.text not in lookup |
| 命名重複 / 目標已存在 | `#ffc8a6` 橘 | seen 衝突 |
| OCR 不一致 / 校正過 | `#e5f0ff` 淺藍 | message 含「校正」「不一致」 |
| 未判讀 | `#e8e8e8` 灰 | result.text == "" |

並在狀態欄左側放一個 4px 寬的色條(同色),讓使用者排序後也能一眼分群。

### 4.3 使用者手動修正後解除警告

目前 `_on_item_changed` 在第 3/4/5 欄改動時呼叫 `_clear_review_issue(row, "使用者手動修正")` — **這是對的**。但有兩個小漏洞:

- 使用者把流水號改回原本錯的值,警告也被清掉(因為 `_clear_review_issue` 不檢查內容)。應該保留原本警告或再驗一次。
- `_clear_review_issue` 沒同步把「判讀信心」欄置灰(顯示「已手動覆寫」)。

### 4.4 「只看問題列」模式

目前沒有。建議:命名表上方加一個 toggle:`[全部 (N)] [問題列 (M)]`,點切換時 `setRowHidden(row, not has_issue)`。同時加 `Ctrl+F` 開過濾文字框(在 old name / new name 上搜尋)。

### 4.5 dry-run 報告

目前 `_execute` 確認對話框是:

```
確定要更名 N 個 PDF?
```

**完全不夠**。建議改成一個小 dialog 列出:

```
即將更名 24 個 PDF (跳過 6 個未變更):

✓ combine_p001.pdf → 101--1-S11U-AI-00001-001.pdf
✓ combine_p002.pdf → 102--1-S11U-AI-00001-002.pdf
...
⚠ combine_p007.pdf → 107--1-S11U-AI-00007-001.pdf  (信心 0.62)
✗ combine_p008.pdf → 缺少命名,將跳過

[匯出計畫 csv] [取消] [確認更名]
```

「匯出計畫 csv」很重要 — 工程師事後追查用得到。

---

## 5. 建議新功能(P0 / P1 / P2)

### 5.1 P0 — 應立即做,能明顯降低出錯

| # | 功能 | 為什麼 |
| - | - | - |
| P0-1 | **判讀流程改成「每張圖二階段」** — 先全圖找「流水號」label,失敗才用 profile ROI | 目前只在按「自動校準框」時跑,正常批次判讀不用 → 浪費既有能力 |
| P0-2 | **批次判讀改 QThread + 進度對話框 + 取消** | 目前 30 頁以上 UI 整個鎖死,無法取消 |
| P0-3 | **預覽暫存 cache**(同 path 不重複 copy + 不重新 render) | 切換命名表列卡頓 |
| P0-4 | **校準 profile 持久化** — ROI、pattern、confidence threshold、最近使用過的 ISO list 路徑,以資料夾為 key 存到 state.json | 使用者每次重開要重設,折損信任 |
| P0-5 | **「只看問題列」過濾** + **狀態多色高亮** | 30 頁以上時找問題列很痛苦 |
| P0-6 | **dry-run 報告 + 計畫匯出 csv** | 套用更名前後沒留紀錄,出錯難 trace |
| P0-7 | **`_is_digit_candidate` 加 fill_ratio 上限 + aspect ratio 限制** | 直接降低邊框誤判 |

### 5.2 P1 — 下一輪,能明顯加速

| # | 功能 | 為什麼 |
| - | - | - |
| P1-1 | **命名表改 QAbstractTableModel + Sort/Filter Proxy** | 純 QTableWidget 在 100 列以上慢且難加欄篩選 |
| P1-2 | **狀態改 enum + 數值化信心欄** | 可排序、可篩選 |
| P1-3 | **ISO List mapping 改成 inline mini-preview**(欄選擇 + 該欄前 3 筆值) | 避免欄名雷同時選錯 |
| P1-4 | **撤銷上一次更名**(rename plan 存到 state.json,單次 undo) | 套用後發現整批錯,只能手動回名 |
| P1-5 | **`_score_iso_sheet` 改 lazy** — 只比 sheet 名稱,不預讀內容 | 大 workbook 卡 |
| P1-6 | **流水號自動校正規則暴露成 plugin 設定**(目前 0.88 信心上限、`max_trim=2` 寫死) | 不同專案可調 |
| P1-7 | **rename 衝突自動 suffix**(目標已存在時提示 `name (2).pdf`) | 目前直接阻擋,使用者得自己處理 |
| P1-8 | **批次判讀完成後在 Terminal 加總結卡片**(N 成功 / M 需確認 / K 失敗 + 連結點到首列) | 目前資訊散落 |

### 5.3 P2 — 未來

| # | 功能 | 備註 |
| - | - | - |
| P2-1 | **替換 RapidOCR 成本地 ONNX 數字模型**(PaddleOCR-Lite 或自訓 7-segment-ish) | 工程圖數字格式相對單純,專用模型可能比通用 OCR 準 |
| P2-2 | **Active learning**:使用者手動修正後存(image_hash, correct_serial),下次同 hash 直接使用 | 重複看同一份 PDF 時免再判讀 |
| P2-3 | **多專案 profile 切換 UI** + project metadata(客戶/圖框類型/解析度) | 同公司多客戶圖框時切換 |
| P2-4 | **圖紙標題欄樣板學習**:每次校準成功時記下「流水號 label 與右上角的相對位置」,累積成樣板;新圖優先用樣板 | 比每張圖跑一次 RapidOCR 找 label 快 |
| P2-5 | **PDF 內嵌 metadata 寫入**(更名同時把 serial / line_no 寫到 PDF /Info) | 下游檔案管理系統可用 |
| P2-6 | **與工具列 context 串接**:在 Explorer 右鍵 → 直接帶 ISO list 路徑 | 已有 context_inbox,差最後一哩 |

---

## 6. 重構方案 — `iso_pdf_naming_dialog.py` 拆分

目前 1629 行單檔,包含主對話框 + RegionSelector + 8 個 helper function + QSS。建議新建 `launcher/ui/iso_pdf/` 子套件:

```
launcher/ui/iso_pdf/
  __init__.py              # 對外只 export IsoPdfNamingDialog
  dialog.py                # IsoPdfNamingDialog,只做組裝、連 signal
  source_panel.py          # 「PDF 來源與拆頁」group
  iso_panel.py             # 「ISO List 與命名」group
  preview_panel.py         # PDF 預覽 + 按鈕 + 裁切預覽
  region_selector.py       # RegionSelector widget(目前在 dialog 檔內)
  naming_table.py          # QTableWidget 包裝 + 高亮邏輯(短期)
  naming_model.py          # QAbstractTableModel(中期)+ NamingRow / Status enum
  validation.py            # _unresolved_review_rows、dry-run 計畫產生
  styles.py                # QSS 樣式(從 _apply_style 抽出)
```

業務邏輯改放回 plugin 那邊:

```
launcher/plugins/iso_tools/
  iso_naming.py            # 既有,不動
  serial_vision.py         # 既有,不動
  serial_correction.py     # 新:_correct_result_with_iso_lookup、_serial_lookup_correction
                           # (從 iso_pdf_naming_dialog.py 搬過來,UI 不該擁有業務邏輯)
  profile.py               # 新:IsoNamingProfile dataclass + load/save 到 state.json
  detect_pipeline.py       # 新:把「拿到 PDF path → QPdfDocument → render → detect」整段抽成 worker-friendly 函式,
                           #     讓批次 QThread 與單張用同一條路徑
```

對應的測試:

```
tests/test_serial_correction.py     # 從 test_iso_vision_correction.py 改 import
tests/test_iso_profile.py           # 新:profile load/save round trip
tests/test_detect_pipeline.py       # 新:給一個 fixture PDF + region,驗 result
tests/test_naming_model.py          # 新:狀態 enum + dry-run plan generator
```

### 6.1 拆分後 dialog 主檔大致長度

| 模組 | 估計行數 | 內容 |
| - | - | - |
| `dialog.py` | ~250 | 組裝面板 + signal 連線 + run/execute 大流程 |
| `source_panel.py` | ~120 | 5 顆來源按鈕 + 路徑顯示 + 拆頁邏輯 |
| `iso_panel.py` | ~200 | ISO 載入、sheet/欄位下拉、套用、產生命名 |
| `preview_panel.py` | ~250 | QPdfView + 9 顆按鈕 + 裁切預覽 + RegionSelector signals |
| `region_selector.py` | ~170 | 從現檔 RegionSelector 搬過來 |
| `naming_table.py` | ~200 | 表格 + 高亮 + 過濾 + 狀態欄產生 |
| `validation.py` | ~80 | dry-run plan + 阻擋邏輯 |
| `styles.py` | ~150 | QSS |

合計約 1400 行,但分散後**每個檔都可獨立 review、獨立測試**,且第二批 P1 改 model/view 也只動 `naming_model.py`,不會炸掉整個 dialog。

### 6.2 拆分順序(避免大爆炸 PR)

| Step | 動作 | PR 大小 |
| - | - | - |
| **S1** | 把 RegionSelector + 全部 `_xxx` module-level helper 搬到 `region_selector.py` + `styles.py`,dialog 檔只 import | 小,~300 行移動 |
| **S2** | 把 `_correct_result_with_iso_lookup` / `_serial_lookup_correction` 搬到 `plugins/iso_tools/serial_correction.py`,改 test import | 小 |
| **S3** | 抽 `naming_table.py`(包 8 欄高亮 + status 產生),先用 QTableWidget,還沒換 model | 中 |
| **S4** | 抽 `preview_panel.py`、`source_panel.py`、`iso_panel.py` 各自成 QWidget,dialog 只負責組合 | 中 |
| **S5** | 新增 `profile.py`、`detect_pipeline.py`,接到 dialog | 中 |
| **S6** | 換 `naming_model.py`(QAbstractTableModel) — P1 工作 | 大 |

---

## 7. 給 Codex 的下一輪實作清單

> 每個 task 都可獨立做、可獨立測試、不互相 block(除了標 `dep` 的)。

### Task A — 把業務邏輯從 UI 檔搬到 plugin

**修改檔案**
- `launcher/ui/iso_pdf_naming_dialog.py` — 移除 `_correct_result_with_iso_lookup`、`_serial_lookup_correction`
- `launcher/plugins/iso_tools/serial_correction.py` — **新檔**,放這兩個函式
- `tests/test_iso_vision_correction.py` — 改 import 來源

**預期行為**:行為不變;UI 檔減少 50 行;測試仍通過。

**風險**:低。`_serial_lookup_correction` 用到 `IsoRecord` 已經在 plugin 端,沒有循環 import。

**建議測試**:
- 既有 `tests/test_iso_vision_correction.py` 應 100% 通過。
- 加一個 `test_serial_correction_no_iso_list`(空 lookup 直接返回原 result)。

---

### Task B — `IsoNamingProfile` 持久化 (P0-4)

**修改檔案**
- `launcher/plugins/iso_tools/profile.py` — **新檔**:`@dataclass IsoNamingProfile(serial_region, confidence_threshold, pattern, iso_list_path, sheet_name, serial_col, line_col)`,with `load_for_folder(folder) -> IsoNamingProfile` / `save_for_folder(folder, profile)`,寫入 `state.json` 的 `iso_naming_profiles` 子節點(key 為資料夾絕對路徑)。
- `launcher/core/state_store.py` — 加 `iso_naming_profile(folder: Path) -> dict | None` / `set_iso_naming_profile(folder: Path, payload: dict)`。
- `launcher/ui/iso_pdf_naming_dialog.py` — 在 `_load_context` / `closeEvent` / 「自動校準框」「套用欄位」之後呼叫 `save_for_folder`;開啟時 `load_for_folder` 套用 ROI / pattern / iso_list / threshold。

**預期行為**:使用者調好 ROI、選好 ISO List、套用欄位後,下次開啟同一個 page_folder,所有設定都被還原。

**風險**:中。要小心 dataclass <-> dict 序列化(Path 要轉 str),且 state.json 容量會慢慢長大 — 限制最多保留 50 個 folder profile,LRU。

**建議測試**:
- `tests/test_iso_profile.py`:round-trip(dataclass → dict → dataclass)、LRU 上限、Path 序列化、不存在 folder 回 None。

---

### Task C — 預覽暫存 cache (P0-3)

**修改檔案**
- `launcher/ui/iso_pdf_naming_dialog.py` — `_copy_pdf_for_preview` 改成:用 `(source_path, source_mtime, source_size)` 當 key,已 cache 過就不複製;`_show_pdf_preview` 在切到已 preview 過的同一 path 時不重新 close+load,直接 set page index。

**預期行為**:切列(同一 folder 內已 cache PDF)即時切換,不再卡 200–500 ms。

**風險**:低。要記得 `closeEvent` 仍要清 temp dir。

**建議測試**:手動驗證 + 加一個 `tests/test_preview_cache.py` 對 `_copy_pdf_for_preview` 做兩次 call 後驗 temp dir 內只有一份檔(可重構成可測試的 helper class `PreviewCache`)。

---

### Task D — 批次判讀改 QThread + 進度對話框 (P0-2)

**修改檔案**
- `launcher/ui/iso_pdf_naming_dialog.py` — `_batch_detect_serials` 改成建立 `BatchDetectThread(QThread)` + `QProgressDialog(self)`;每張完成 emit `progress(i, n, path, result)`,UI 即時更新該列;`progress_dialog.canceled.connect(thread.cancel)`。
- 新增 `launcher/ui/iso_pdf/batch_detect.py`(或暫時放主檔)— `BatchDetectThread` 與 cancel-aware 主迴圈。

**預期行為**:批次判讀過程中表格逐列更新;進度對話框顯示「3 / 24 處理中」;按取消立刻停下,已判讀的列保留。

**風險**:中。`detect_serial_from_qimage` 在子執行緒裡跑要小心 QPdfDocument 是不是 thread-safe — 簡單做法:子執行緒不用 QPdfDocument,直接 `pypdf` + `pdfium` 或把 QPdfDocument 操作排回 UI thread 用 `QMetaObject.invokeMethod`(更複雜)。第一版可以 worker thread 內呼叫一個 module-level function 透過 `QPdfDocument(None)` 建立 + load(可行,目前 `_detect_serial_from_pdf` 就在做),測試會證明能不能跑。

**建議測試**:
- 手動拿 30 頁 PDF 跑,觀察 UI 響應、取消行為、resulting rows。
- 單元測試補 `BatchDetectThread.cancel` 在第 N 張前後是否真的停下。

---

### Task E — 每張圖二階段判讀 (P0-1)

**修改檔案**
- `launcher/plugins/iso_tools/serial_vision.py` — 新增 `detect_serial_two_stage(image, fallback_region) -> SerialVisionResult`:先 `calibrate_serial_region_from_bgr(image)` 拿 ROI,成功用該 ROI 跑 `detect_serial_from_bgr`,結果無文字或低信心再用 `fallback_region`。
- `launcher/ui/iso_pdf_naming_dialog.py` 與 batch:改呼叫 `detect_serial_two_stage`。
- 保留現有 `detect_serial_from_qimage` 不變(行為兼容),避免動到既有測試。

**預期行為**:不同圖紙、流水號位置不同時也能找到;判讀 message 帶「自動 ROI:來自流水號 label」或「fallback ROI」。

**風險**:中。每張圖多跑一次 RapidOCR,**速度會慢約 1.5–2 倍**;需在 profile 加 `two_stage_enabled: bool = True` 讓使用者可關。

**建議測試**:
- `tests/test_serial_vision.py` 補 `test_two_stage_uses_calibrated_region_when_label_found` + `test_two_stage_falls_back_to_default_region`。

---

### Task F — `_is_digit_candidate` 加 aspect ratio + fill_ratio 上限 (P0-7)

**修改檔案**
- `launcher/plugins/iso_tools/serial_vision.py` — `_is_digit_candidate`:加 `0.20 < width / max(1,height) < 1.2` 與 `fill_ratio < 0.85`。

**預期行為**:純色塊邊框(fill_ratio ≈ 1.0)與長條框線(aspect 失衡)被擋掉。

**風險**:低。但要對既有 fixture 驗證沒回歸。

**建議測試**:
- `tests/test_serial_vision.py` 新增 `test_solid_block_is_not_a_digit`(製造一個 50×60 純黑塊放右上,期望結果 text=="" )。
- 既有 5 個正面 test 全部 pass。

---

### Task G — 命名表「只看問題列」過濾 + 多色高亮 (P0-5)

**修改檔案**
- `launcher/ui/iso_pdf_naming_dialog.py` — 在 `_build_table_panel` 上方加一條 toolbar:`[全部 N] [問題列 M] [搜尋:_____]`;`_refresh_statuses` 結尾根據 filter mode 呼叫 `setRowHidden`;`_apply_row_review_style` 依 `_review_issue_kind(reason)` 回傳不同 QColor。
- 加 `_review_issue_kind(reason: str) -> str`:傳回 `low_confidence` / `not_in_iso` / `conflict` / `correction`。

**預期行為**:使用者可即時切「只看問題」;不同問題不同顏色;搜尋框打字立即過濾 old/new name。

**風險**:低。但要小心 `setRowHidden` 與 `setCurrentCell` 互動(隱藏列被選中時要跳下一個未隱藏列)。

**建議測試**:
- 手動 + `tests/test_naming_filter.py`:給定 mock review_issues dict,驗 `_review_issue_kind` 分類正確。

---

### Task H — dry-run 報告 + 計畫匯出 (P0-6)

**修改檔案**
- `launcher/ui/iso_pdf/validation.py` — **新檔**:`build_rename_plan(operations, vision_results, review_issues) -> RenamePlan`;`RenamePlan.to_markdown()`、`RenamePlan.to_csv()`。
- `launcher/ui/iso_pdf_naming_dialog.py` — `_execute` 在 `QMessageBox.question` 之前改顯示 `RenamePlanDialog(self, plan)`,讓使用者看完整清單、可匯出 csv,再按確認。

**預期行為**:套用前必看完整計畫;可匯出 csv 留底。

**風險**:低。新 dialog,不動既有路徑。

**建議測試**:
- `tests/test_rename_plan.py`:給 RenameOperation 序列,驗 plan to_csv 內容正確、warning rows 包含信心 < threshold 的列。

---

### Task I — 拆檔(S1+S2) — 結構性重構

**修改檔案**
- 新建 `launcher/ui/iso_pdf/__init__.py`、`region_selector.py`、`styles.py`。
- `launcher/ui/iso_pdf_naming_dialog.py` 減重至 ~1200 行(以後再降)。
- 改變 `from launcher.ui.iso_pdf_naming_dialog import RegionSelector` 的外部引用(目前沒有,但日後 grep 一次確保)。

**預期行為**:行為完全不變;dialog 檔變小;`RegionSelector` 與 QSS 各自獨立。

**風險**:低。純搬家 + import 調整。

**建議測試**:既有所有測試應該 pass;額外加 `tests/test_region_selector_imports.py` 用 `import launcher.ui.iso_pdf.region_selector` 驗模組可載入。

---

## 8. 建議的執行順序

```
S1: Task A  + Task I   (重構,小,先做)
S2: Task F + Task C    (P0 容易做、立刻有感)
S3: Task B             (Profile 持久化,中)
S4: Task G + Task H    (UX,中)
S5: Task D + Task E    (批次判讀執行緒 + 二階段,大)
```

每個 task 後跑 `python -m unittest discover tests`,確保沒回歸再進下一個。

---

## 9. 我刻意沒建議的事(配合你給的避免清單)

- **不重寫為 Electron / Web**:現在 PyQt6 + QPdfDocument + opencv + RapidOCR 整個 stack 在 Windows 上已可用,改 stack 會把 QPdfView + RapidOCR + 系統字型一起賠掉。
- **不單純「加 AI」**:P2 提到 ONNX 數字模型與 active learning,都是具體可實作項;不是泛談 LLM。
- **不破壞既有可用流程**:Task A–I 都向後相容,既有 `detect_serial_from_qimage` 函式簽名不變、`IsoRecord` schema 不變、state.json 不刪欄。
- **不忽略它是常駐工具**:批次改執行緒、Profile 持久化、預覽 cache 都圍繞「使用者每天開、要快、不能 freeze」這個前提。
