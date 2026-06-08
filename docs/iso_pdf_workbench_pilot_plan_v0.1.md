# ISO PDF 拆頁命名 — 三層工作台 + 失敗復原 先導計畫 v0.1

> 寫作角度:**一鍵(Autopilot)已趨穩定,要被保護;工作台(Workbench)與調校(Engineer)還不穩,要重新分層;一鍵失敗時,工作台要能讀 run log / pilot list 還原現場讓工程師救援。**
> 本文是「先導計畫」,具體到 UI 區塊、資料欄位、流程、狀態、測試與模組切分,可直接拆成 Codex 任務。

## 對接文件
- `docs/iso_pdf_workbench_audit.md`(舊版 PyQt UX/OCR 痛點)
- `docs/iso_pdf_workbench_next_stage_v0.1.md`(Autopilot/Workbench 分層、IssueCode、狀態機、安全機制的原始藍圖)
- `docs/ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md`(舊→新 parity 盤點與下架路線)
- `docs/iso_pdf_workbench_blueprint_v0.2.md`、`docs/ui_uplift_proposal_v0.1.md`(設計 token / 版面)

## 對接程式碼(現況,已存在)
- 前端:`frontend/tauri-spike/src/App.tsx`(3051 行,`IsoPdfAutopilot` god component)、`src/isoWorkflow.ts`(型別 + invoke 封裝)、`src/legacy.ts`(舊版橋接)
- 橋接:`launcher/app/tauri_iso_workflow.py`(12 個 action)、`launcher/app/tauri_iso_worker.py`(批次判讀 worker,寫 `job.json`)、`launcher/app/tauri_iso_preview.py`(預覽)
- 邏輯:`launcher/plugins/iso_tools/{iso_naming,serial_vision,serial_correction,profile,rename_plan,validator,issues}.py`
- 舊版 PyQt(保留為 legacy/對照/測試):`launcher/ui/iso_pdf/{batch_detect,region_selector,result_dialog,styles}.py`、`launcher/ui/iso_pdf_naming_dialog.py`
- 狀態儲存:`launcher/core/state_store.py`(`iso_naming_profile()` / `set_iso_naming_profile()`)

## 邊界(來自需求,務必遵守)
1. **不拔 PyQt6**:舊版保留為 legacy / 對照 / 測試路線,只逐步讓橋接鈕從主動線退到「調校 > 進階」。
2. **不把一鍵變複雜**:一鍵畫面元素只增不減地「保護」,任何工程資訊都不准進一鍵主畫面。
3. **工作台可複雜,但要分層**:危險操作(套用更名、覆蓋、清 profile)要有閘門與權限層,一般使用者不可能誤按。
4. **調校資料可回復、可追蹤、可匯出**:每次調 ROI / 門檻 / 欄位都要能 revert、能在 run log 看到、能匯出問題包。
5. **可落地 Windows + Tauri + Python**:沿用現有 `run_iso_workflow` action 協定與 `job.json` 檔案串流,不另起爐灶。

---

## 0. 現況快照與三個真正缺口

先講「已經有的」,避免重複建議已完成的工作。

### 0.1 已經做好的(本計畫不重做,只強化)

| 能力 | 現況位置 |
| --- | --- |
| 三層模式切換(一鍵/工作台/調校) | `App.tsx` `isoView: "autopilot" \| "workbench" \| "engineer"` segmented control |
| 一鍵狀態機(雛形) | `oneClickStage: "idle" \| "running" \| "applying" \| "review" \| "done"` |
| 12 個後端 action | `tauri_iso_workflow.py`:`discover_sources / split_pdf / load_iso_table / plan / build_rename_plan / export_plan_csv / start_batch_detect / job_status / cancel_job / apply / load_profile / save_profile` |
| 批次判讀檔案串流 | `tauri_iso_worker.py` 寫 `.runtime/jobs/iso/<job_id>/{job.json,request.json,cancel.json}`;state `queued/running/cancel_requested/cancelled/completed/failed`;`progress{total,done,percent}` + `events`(ROW_DONE) |
| Profile 依資料夾持久化 | `profile.py` `IsoNamingProfile` + `state_store` |
| ROI 滑桿 + 重設 | 調校頁 `serialRegion/drawingRegion` + `resetRoi()`,預設 serial `{0.62,0,0.38,0.24}` / drawing `{0.5,0.66,0.5,0.34}` |
| 預覽 cache | `previewCacheRef`(key = path\|detect\|serialRegion\|drawingRegion) |
| dry-run + CSV | `dryRunOpen` + `export_plan_csv`(13 欄 CSV,utf-8-sig) |
| 逐列複核閉環(雛形) | `adoptPreviewVision()`(採用判讀值)、`confirmSelectedRow()`(確認此列) |
| 起飛 checklist | `validator.py` 7 閘門 `validate_autopilot_checklist()` + `issues.py` `ChecklistIssue`(碼 PF01-08/E001-06/W001-03) |

### 0.2 三個真正缺口(本計畫的主軸)

1. **失敗復原斷鏈**:`job.json` 是暫態的(job 目錄會被清、無 `run_id` 索引、無 replay payload、無 debug bundle)。一鍵一旦失敗,工程師**無法還原現場**,只能重跑或跳舊版 → 這是工作台「不穩」的根因。
2. **沒有夠細的 Pilot List**:目前只有 7 條 checklist。需求要的是 **17 條診斷項**(input discovery → … → export report),每條有成功/警告/阻擋條件、雙層文案、可自動修復 vs 需人工。
3. **調校缺安全層**:ROI 只有滑桿(無拖框 overlay、無多頁採樣、無 confidence heatmap、無 preset),且**調校會直接污染一鍵預設**(沒有「草稿層 vs 已發布層」之分),也**不能 revert 上一版**。

> 本計畫 = 把這三條補起來,並把 3051 行的 `App.tsx` god component 依三層拆開,讓「一鍵穩定區」與「工作台/調校開發區」在程式碼上也分家。

---

## 1. 角色與產品邊界

### 1.1 三層模型(維持現有三分,但重新定義邊界)

| 維度 | 一鍵 Autopilot | 工作台 Workbench | 調校 Engineer / Pilot |
| --- | --- | --- | --- |
| 對象 | 長官、一般同事、重複作業 | 資料校對者、問題排查者 | 開發者、工程師(新圖框、改判讀邏輯) |
| 心智 | 「選資料夾,其餘交給它」 | 「逐列把問題消掉」 | 「定位 root cause、調參數、重跑」 |
| 主畫面 | pipeline 6 格 + 一顆情境主按鈕 + event log | 命名表(主)+ PDF 校對(放大) | ROI/欄位/門檻/Profile/Pilot List/Run Log |
| 停下來時機 | 只在低自信、衝突、blocked | 每列都可介入 | 每個 pipeline 階段都可單步 |
| 可做的危險操作 | 套用更名(全綠自動、有黃燈需勾確認) | 套用更名、逐列改值、確認列 | 全部 + 改 ROI/門檻/欄位 + 發布 profile |
| 絕不出現 | ROI、欄位下拉、pattern、門檻、Run Log、舊版鈕 | ROI 多框編輯器、Pilot 單步、Run Log raw | (無限制) |
| 共用 | **同一份 plan、同一條 pipeline、同一個 `run_iso_workflow` 協定**,差別只在「外殼 + 停下來策略 + 權限」 | | |

### 1.2 一鍵保留 / 絕不出現清單

**一鍵必須保留(這些是它「穩」的本體,動到要回歸測試):**
- 單一情境主按鈕(`oneClickButton`,7 種語意),以及它「全綠一路到底、有黃燈才停」的策略。
- pipeline 6 格(來源 → 拆頁 → 判讀流水號 → 對 ISO → 命名 → 更名),只讀、不可點進去改設定。
- event log(只讀 worker 真實事件,不可變成可編輯終端機)。
- review 階段的「待確認列縮影」+「前往工作台修正 N 筆」導流鈕。
- 「完成 · 再處理一批」收尾。

**一鍵絕不該出現(出現即視為回歸 bug):**
- ROI 滑桿 / 拖框 / 座標數字。
- Sheet / 流水號欄 / 圖號欄下拉、pattern 輸入、confidence 門檻滑桿。
- 「批次判讀」「重新產生」「匯出 CSV」「舊版」這類工程按鈕。
- Run Log / Pilot List / Job protocol / 任何 raw JSON 或 stack trace。
- 任何需要「先讀懂才會用」的欄位。失敗時只給一張卡(見 §7),細節全部留給工作台。

### 1.3 工作台服務的四種角色(同一殼、不同入口深度)

| 角色 | 進入點 | 主要動作 | 對應本文章節 |
| --- | --- | --- | --- |
| 資料校對者 | 工作台(預設) | 掃問題列、改流水號/圖號、確認列、套用 | §2.3、§6 |
| 問題排查者 | 工作台 → Run Log / Pilot 抽屜 | 看一鍵為何失敗、哪個 pilot 紅、還原現場 | §3、§4、§7 |
| 工程師(調參) | 調校 | ROI、欄位對應、門檻、pattern、單步 pipeline | §3、§5、§6 |
| 開發者(改碼) | 調校 → Developer mode | raw run log、replay payload、debug bundle、舊版對照 | §2.6、§4 |

### 1.4 是否做成三層?→ 是,但用「同殼三視圖 + 一條 Developer 開關」

- 維持現有 segmented control(一鍵 / 工作台 / 調校)**不另開視窗**,三者共用 plan 與 pipeline。
- 在「調校」內再加一個 **Developer mode 開關**(預設關;開啟後才顯示 Run Log raw、replay、debug bundle、舊版對照)。這樣「工程師調參」與「開發者除錯」也分層,一般工程師不會被 stack trace 淹沒。
- 結論:**一鍵 / 工作台 / 調校(內含 Developer 子層)= 實質四層,但對使用者只露三顆 tab + 一個開關。**

---

## 2. 建議資訊架構

整體沿用 `ISO工作台_舊版轉新版…v0.1.md §4.2` 的「設定軌 + 命名表 + PDF 校對放大」三段,但把三視圖的左/中/右明確定義,並加上 debug 抽屜。

### 2.1 一鍵(Autopilot)版面 — 維持,僅微調

```
┌ 頂列:標題 · 三視圖切換(一鍵|工作台|調校) ───────────────────────┐
│ (一鍵視圖不顯示來源 strip、不顯示舊版鈕)                          │
├──────────────────────────────────────────────────────────────────┤
│ pipeline 6 格(只讀):來源→拆頁→判讀流水號→對ISO→命名→更名         │
├──────────────────────────────────────────────────────────────────┤
│ [review 時才出現] 待確認列縮影 + 命名衝突提示                       │
├──────────────────────────────────────────────────────────────────┤
│            ████  情境主按鈕(7 種語意)  ████                        │
│            一行 hint                                                │
├──────────────────────────────────────────────────────────────────┤
│ event log(只讀,自動捲到底)                                        │
└──────────────────────────────────────────────────────────────────┘
```

- 左/右欄在一鍵視圖**不存在**(目前已是如此,要守住)。
- 失敗時,event log 末尾出現一張「失敗卡」(§7),含三顆鈕:`交給工程師`、`匯出問題包`、`開啟調校工作台`。

### 2.2 左中右分配總表

| 視圖 | 左 | 中 | 右 |
| --- | --- | --- | --- |
| 一鍵 | (無) | pipeline + 主按鈕 + event log | (無) |
| 工作台 | 設定軌(可收合,產生草稿後收成摘要 chip) | 命名表(主,~46%) | PDF 校對 + 逐列動作(~40%,放大) |
| 調校 | 來源 + Quality gates + **Pilot List** 入口 | ISO 對映 + Job protocol + **Run Log** | PDF 校對 + ROI 編輯器 + Profile 發布 + Legacy 對照 |

### 2.3 工作台(Workbench)版面

```
┌ 頂列:三視圖切換 · 單一情境主按鈕 · [收合到 dock] ──────────────────┐
├ 左:設定軌(可收合 260px) ┬ 中:命名表(主) ┬ 右:PDF 校對(放大) ──┤
│ ▸ 來源摘要 chip          │ 指標列(1 行)   │ 整頁 PDF(大)           │
│ ▸ ISO/欄位摘要 chip      │ 工具列:搜尋·只看問題·全選 │ 右上流水號 ROI(只讀框)│
│ ▸ Profile chip          │ 命名表:Use·Page·Old·  │ 右下圖號 ROI(只讀框)  │
│   (點開才展開設定)       │   Serial·Line·Conf·   │ vision 讀數 + 候選     │
│                         │   Status·New          │ 逐列:[採用判讀][確認列][下一個問題] │
├ 底:事件 log(可收合,預設一行) ────────────────────────────────────┤
└────────────────────────────────────────────────────────────────────┘
```

要點:
- **命名表 + PDF 校對是兩個主角**;ROI 在工作台是**只讀預覽框**(看判讀對不對),真要拖框去「調校」。這條界線讓校對者不會誤改 ROI。
- 命名表加 audit §4.2 的 **5 類問題分色**(低信心黃 / ISO 無此號紅 / 重複橘 / 校正藍 / 未判讀灰)與**信心欄(可排序)**。
- 「下一個問題」改成**循環**(目前 `chooseProblemRow` 只跳第一個)。

### 2.4 調校(Engineer)版面 + Debug Drawer

```
┌ 頂列:三視圖切換 · [Developer mode ▢] ──────────────────────────────┐
├ 左:來源 + Quality gates + ▸開啟 Pilot List ┬ 中:ISO 對映 + Job protocol + ▸Run Log ┬ 右:ROI 編輯器 + Profile 發布 + Legacy ┤
└─────────────────────────────────────────────────────────────────────┘
  ▸ Pilot List / Run Log / Debug bundle 以「右側滑出抽屜(drawer)」呈現,不佔主版位
```

- **Pilot List 抽屜**(§3):點某 pilot 列 → 右側滑出該 pilot 的雙層說明 + 修復鈕。
- **Run Log 抽屜**(§4):列出最近 N 筆 run,點進去看時間軸 + 失敗階段 + replay/匯出。
- **Developer mode 開**才顯示:run log raw JSON、replay payload、debug bundle、舊版對照(`legacy.launch`)。**Developer mode 關**時,舊版鈕收進這裡(從工作台主動線移除),達成「逐步下架舊版」又不立刻拔掉。

### 2.5 tabs / stepper / drawer / developer-only 決策表

| 元件 | 形式 | 理由 |
| --- | --- | --- |
| 一鍵 / 工作台 / 調校 | **segmented tabs**(已存在) | 三種心智,需隨時切換 |
| pipeline 來源→…→更名 | **stepper(只讀)** | 線性流程、表達進度;一鍵與工作台共用 |
| Pilot List | **drawer + 可展開列** | 17 條太多,不能佔主版位;點開才看細節 |
| Run Log | **drawer + 時間軸** | 偶爾才看;要能翻歷史 run |
| ROI 編輯器 | **右欄 inline + 拖框 overlay** | 調校核心動作,值得常駐右欄 |
| Profile 發布 / diff | **modal** | 危險、低頻,需要確認 |
| raw JSON / replay / debug bundle | **developer-only**(Developer mode 開) | 嚇人、易誤解 |
| 舊版橋接 | **developer-only**(過渡期) | 逐步退出主動線 |

### 2.6 如何避免一般使用者被工程資訊嚇到

1. **預設只露一鍵**:首次進入 ISO 頁預設 `isoView="autopilot"`(目前如此)。
2. **顏色語意一致**:全程沿用 `ready/warn/blocked/idle` 四態 + 五類分色,不在一鍵出現紅黃綠以外的工程色票。
3. **文案雙層**:每個診斷項都有「一般文字」(see §3 欄位 `user_text`)與「工程診斷」(`engineer_detail`);一鍵與工作台只顯示 `user_text`,調校才顯示 `engineer_detail`。
4. **危險操作藏深**:覆蓋(overwrite)、清 profile、發布 profile、replay 都在調校且需二次確認;一鍵完全沒有入口。
5. **Developer mode 一個開關收掉所有 raw**:沒開就看不到 JSON / stack / replay。

---

## 3. Pilot List / Diagnostic Plan

Pilot List = 把一條 pipeline 拆成可單獨檢查、單獨重跑、單獨報告的**診斷項**。它同時是:(a) 起飛前的 preflight、(b) 跑的時候的進度、(c) 失敗後的「哪一格紅了」定位表。

### 3.1 資料模型(建議新增 `iso_tools/pilot.py`)

```python
# launcher/plugins/iso_tools/pilot.py（新增）
PilotStatus = Literal["pending", "running", "ready", "warn", "blocked", "skipped"]

@dataclass(frozen=True)
class PilotItem:
    id: str                      # "P03_split"
    name: str                    # 顯示名
    stage: str                   # discover/source/split/iso/mapping/detect/match/plan/apply/report
    status: PilotStatus
    user_text: str               # 給一般使用者(一鍵/工作台)
    engineer_detail: str         # 給工程師(調校);可含數字、路徑、欄位
    metrics: dict[str, Any]      # {"pdf_count":18,"avg_conf":0.78,...}
    auto_fix: str | None         # 可自動修復動作的 action id（None=不能自動修）
    manual_hint: str | None      # 需人工調整時的指示
    blocks_apply: bool
    issue_codes: tuple[str, ...] # 對應 issues.py 的 PF/E/W 碼

@dataclass(frozen=True)
class PilotReport:
    run_id: str
    created_at: str
    items: tuple[PilotItem, ...]
    failed_stage: str | None
```

後端新增 action `pilot_report`(走同一個 `run_iso_workflow` 協定),回傳 `PilotReport`;前端在「調校 > Pilot List 抽屜」與「失敗卡 > 展開」呈現。它**重用**現有 `validate_autopilot_checklist()` 的 7 條,再補到 17 條。

### 3.2 Pilot List 17 項(完整規格)

> 欄位:**目的 / 輸入 / 成功(ready) / 警告(warn) / 阻擋(blocked) / user_text / engineer_detail / 自動修復 / 人工調整**

#### P01 input discovery(來源探索)
- 目的:從工作資料夾推斷 combine PDF / page folder / ISO List。
- 輸入:`work_folder`(或 combine/page)。
- ready:三者至少推斷出 PDF 來源 + ISO List。warn:只找到 PDF 沒找到 ISO。blocked:資料夾不存在/不可讀。
- user_text:「已找到 PDF 與 ISO List」/「找不到 ISO List,請手動選」。
- engineer_detail:列出 `_auto_combine_pdf_candidate` 命中檔、`_nearby_iso_list_candidates` 評分前 3。
- 自動修復:`discover_sources`。 人工:手動指定來源。
- issue:PF01 / E001。

#### P02 PDF source check(PDF 來源檢查)
- 目的:確認來源 PDF 存在、可讀、頁數>0。
- 輸入:combine_pdf 或 page_folder。
- ready:可讀且 ≥1 頁。warn:是 combine,啟動會拆頁。blocked:不存在/0 頁/讀取失敗。
- user_text:「PDF 可讀(18 頁)」/「PDF 打不開」。
- engineer_detail:檔大小、頁數、是否既有 `_pages`、pypdf 例外訊息。
- 自動修復:用既有拆頁;否則 `split_pdf`。 人工:重選 PDF。
- issue:PF02 / E002。

#### P03 page split check(拆頁檢查)
- 目的:確認 combine → 單頁 PDF 數量正確、無 0KB 壞頁。
- 輸入:combine_pdf。
- ready:輸出頁數 = 來源頁數。warn:重用既有 `_pages`(可能過期)。blocked:拆出 0 頁或檔案被鎖。
- user_text:「已拆成 18 頁」。
- engineer_detail:來源頁數 vs 輸出頁數 vs 既有頁數,`_pages` 路徑與 mtime。
- 自動修復:刪舊 `_pages` 重拆。 人工:檢查 combine 是否毀損。
- issue:PF02。

#### P04 ISO list parse check(ISO 解析)
- 目的:能讀到 workbook、列出 sheet。
- 輸入:iso_list。
- ready:成功讀檔且 ≥1 sheet。warn:多 sheet 需挑選。blocked:檔不存在/非 xlsx/csv/解析失敗。
- user_text:「ISO List 已讀取」。
- engineer_detail:sheet 清單 + 每個 sheet 的 `_score_iso_sheet` 分數。
- 自動修復:`load_iso_table`(自動挑分數最高 sheet)。 人工:手選 sheet。
- issue:PF03 / PF04 / E003。

#### P05 sheet / column mapping check(欄位對應)
- 目的:猜出流水號欄、圖號/檔名欄。
- 輸入:選定 sheet 的 headers。
- ready:兩欄都猜到。warn:猜到一欄。blocked:兩欄都猜不到。
- user_text:「已對應流水號與圖號欄」。
- engineer_detail:`guess_iso_columns` 命中 header、各欄前 3 筆樣本值(補 audit §3.3 缺口)。
- 自動修復:`guess_iso_columns`。 人工:在調校用兩個下拉手選。
- issue:PF03 / E003。

#### P06 serial number detection(流水號判讀)
- 目的:對每頁判讀右上流水號。
- 輸入:page PDFs、serial_region、confidence_threshold、detect_serials。
- ready:判讀率 ≥95% 且平均信心 ≥ 門檻。warn:判讀率或信心偏低。blocked:OCR engine 不可用。
- user_text:「流水號判讀完成」/「部分頁信心偏低,需確認」。
- engineer_detail:per-page text/confidence、低於門檻清單、`serial_vision` 兩階段是否命中 label。
- 自動修復:`start_batch_detect` 重判;`correct_result_with_iso_lookup`。 人工:改 ROI(§5)、改門檻、逐列採用。
- issue:PF07 / W001 / E004。

#### P07 drawing number detection(圖號判讀)
- 目的:右下圖號 ROI 判讀 / 由 ISO List 帶出。
- 輸入:drawing_region、ISO lookup。
- ready:圖號取得。warn:圖號空白(靠 ISO 帶)。blocked:無圖號且 ISO 查無。
- user_text:「圖號已對應」。
- engineer_detail:圖號 ROI 裁切讀數、ISO `line_no` 來源。
- 自動修復:由 serial → ISO lookup 帶圖號。 人工:改 drawing ROI、手填圖號。
- issue:W003。

#### P08 ROI confidence(判讀區信心)
- 目的:評估目前 ROI 是否適合此圖框。
- 輸入:多頁 serial/drawing 裁切 + 信心分布。
- ready:多頁信心穩定且高。warn:信心方差大(ROI 偏)。blocked:整批近 0(ROI 完全沒對到)。
- user_text:(一般使用者不顯示;只在調校)。
- engineer_detail:N 頁信心 heatmap、建議位移量(見 §5 自動校準)。
- 自動修復:二階段自動校準(找「流水號」label)。 人工:拖框微調。
- issue:W002。

#### P09 duplicate detection(重複偵測)
- 目的:找出兩頁判到同流水號、或兩列產生同檔名。
- 輸入:rows 的 serial / target_path。
- ready:無重複。warn:有重複但可加後綴。blocked:重複且策略未定。
- user_text:「有 2 個頁面命名重複,需處理」。
- engineer_detail:列出衝突 page 對、衝突 target。
- 自動修復:`on_conflict=append_v` 加 `_v2`(未來項)。 人工:逐列改流水號。
- issue:E004 / E003(對應 `_row_status` 的「目標檔名重複」)。

#### P10 missing serial detection(漏號偵測)
- 目的:找出沒判到、或 ISO List 查無的流水號。
- 輸入:rows + ISO lookup。
- ready:全部有對應。warn:少數暫用頁序。blocked:大量無對應(可能 sheet/欄選錯)。
- user_text:「3 頁暫用頁序,請確認」。
- engineer_detail:無對應 page 清單、暫用頁序規則(見 `_serial_for_row`)。
- 自動修復:無。 人工:採用判讀值、改欄位、或在 ISO List 補列。
- issue:W002(「ISO List 無此流水號」)。

#### P11 naming pattern validation(命名格式驗證)
- 目的:pattern 變數合法、產出檔名合法。
- 輸入:pattern、第一列判讀結果。
- ready:pattern 變數在白名單(`{serial}`,`{line}`)且即時預覽成功。warn:含非法字元會被 sanitize。blocked:pattern 解析失敗或產出空名。
- user_text:(調校才顯示)。
- engineer_detail:即時預覽第一頁檔名、sanitize 前後對照。
- 自動修復:sanitize 非法字元(記 W006)。 人工:改 pattern。
- issue:對應 `_validate_file_name`。

#### P12 rename draft generation(命名草稿產生)
- 目的:`plan` 成功產出 rows + summary。
- 輸入:以上全部。
- ready:草稿產生,blocked=0。warn:有 warn 列。blocked:plan 例外。
- user_text:「已產生命名草稿:N/M 可套用」。
- engineer_detail:summary 計數、各 issue 來源(pdf_events/iso_meta/row_events)。
- 自動修復:`plan` / `build_rename_plan`。 人工:看 P09/P10。
- issue:ROW 事件。

#### P13 blocked rows explanation(阻擋列說明)
- 目的:把每個 blocked 列「為什麼」講清楚。
- 輸入:rows.status=="blocked"。
- ready:無 blocked。blocked:有 blocked(逐列附原因)。
- user_text:「2 個檔案無法更名:目標已存在、缺圖號」。
- engineer_detail:逐列 `note`(來自 `_row_status`:無新名/非法字元/缺 line_no/重複/已存在)。
- 自動修復:依原因給對應 action。 人工:逐列修。
- issue:E003 / E006。

#### P14 manual correction path(人工修正路徑)
- 目的:確保每個 warn/blocked 都「有一條可以消掉它的動作」。
- 輸入:選取列。
- ready:該列可被 `adoptPreviewVision`/`confirmSelectedRow`/`updateRow` 解。
- user_text:「點此列 → 在右側採用或改值」。
- engineer_detail:該列可用動作清單 + 目前阻擋條件。
- 自動修復:採用判讀值。 人工:改 serial/line/new_name、確認列。
- issue:—(流程項)。

#### P15 dry-run / apply path(試算與套用)
- 目的:套用前 dry-run(檢查存在/鎖定/長度),套用為原子批次。
- 輸入:selected rows。
- ready:dry-run 全過。warn:有自動 sanitize/加後綴。blocked:任一筆 dry-run fail。
- user_text:「即將更名 N 個,跳過 M 個」。
- engineer_detail:逐筆 src→dst + risk(`_validate_operations` 結果)。
- 自動修復:重跑 dry-run。 人工:處理失敗筆。
- issue:E006 / E007(路徑長度,未來)。

#### P16 rollback path(回復路徑)
- 目的:套用後能撤銷(目前缺,屬新增)。
- 輸入:本批 `run_id` 的 rename 記錄。
- ready:已寫入可回復記錄(undo log)。blocked:undo 寫入失敗。
- user_text:「可一鍵撤銷此次更名」。
- engineer_detail:undo 記錄路徑、本批 item 數。
- 自動修復:由 run log 反向 rename。 人工:無。
- issue:E008(undo 無法寫入)。

#### P17 export log / report path(匯出報告)
- 目的:能匯出 run log + CSV + debug bundle。
- 輸入:`run_id`。
- ready:可匯出。warn:部分檔缺(如預覽圖)。blocked:匯出目錄不可寫。
- user_text:「已匯出問題包」。
- engineer_detail:bundle 內容清單(§4.4)。
- 自動修復:`export_plan_csv` + 新 `export_debug_bundle`。 人工:選匯出位置。
- issue:—。

### 3.3 Pilot List 與既有 checklist 的關係

- `validator.py` 現有 7 閘門 = P01(folder)、P02(pdf)、P04/P05(iso)、P06(ocr)、P08(profile)、P15(output)、P13(rename)。
- 本計畫把它**擴成 17 條 PilotItem**,並讓 `validate_autopilot_checklist()` 成為 PilotReport 的子集(向後相容,既有 `test_iso_validator.py` 不破)。

---

## 4. Error Log / Run Log 設計

目標:**一鍵失敗後,工作台/調校能用一個 `run_id` 完整還原現場**,工程師不必問「你那時選了什麼、ROI 是多少、ISO 哪個 sheet」。

### 4.1 為什麼現在不夠

現有 `job.json` 只服務「批次判讀」單一階段,且:
- 沒有 `run_id`(只有 `job_id`,且只在批次判讀時建立)。
- job 目錄在 `.runtime/jobs/iso/` 可能被清;沒有「最近 run」索引。
- 失敗只存一個 `error` 字串,沒有 failed_stage、沒有當時完整輸入快照、沒有 pilot 結果。
- 沒有 replay payload、沒有 debug bundle。

### 4.2 Run Log schema(建議新增 `iso_tools/run_log.py`)

每次「產生草稿 / 一鍵 / 批次判讀 / 套用」都開一筆 run,寫成 **JSONL 一行一事件 + 一個 run 摘要檔**。

```jsonc
// .runtime/runs/iso/<run_id>/run.json  （run 摘要,可被 Run Log 抽屜列出）
{
  "run_id": "iso-20260608-143312-3f9a",   // <prefix>-<本地時間>-<短亂數>
  "schema_version": 1,
  "mode": "autopilot",                      // autopilot | workbench | engineer
  "trigger": "one_click",                   // one_click | generate_plan | batch_detect | apply
  "created_at": "2026-06-08T14:33:12+08:00",
  "ended_at": "2026-06-08T14:33:48+08:00",
  "status": "failed",                       // running | completed | warn | failed | cancelled
  "failed_stage": "iso",                    // 對應 pilot.stage / pipeline key,成功為 null
  "input": {                                // 完整輸入快照(可直接 replay)
    "work_folder": "...","combine_pdf": "...","page_folder": "...",
    "iso_list": "...","sheet_name": "ISO List","serial_col": 0,"line_col": 3,
    "pattern": "{serial}--{line}.pdf","detect_serials": true,
    "confidence_threshold": 0.70,
    "serial_region": {"left":0.62,"top":0,"width":0.38,"height":0.24},
    "drawing_region": {"left":0.5,"top":0.66,"width":0.5,"height":0.34}
  },
  "profile": {                              // 當時套用的 profile 來源與內容
    "folder": "...","exists": true,"applied": true,
    "payload": { /* IsoNamingProfile.to_payload() */ }
  },
  "iso_parse": {                            // P04/P05 結果
    "sheet_options": ["Sheet1","ISO List"],"sheet_used": "ISO List",
    "headers": ["流水號","管線","..."],"serial_col": 0,"line_col": 3,
    "record_count": 0,"error": "ISO List 沒有有效資料。"
  },
  "summary": {"total": 0,"ready": 0,"warn": 0,"blocked": 0,"selected": 0},
  "pilot": [ /* PilotReport.items 精簡版:id,status,issue_codes */ ],
  "counts": {"detected": 0,"low_conf": 0,"missing_serial": 0,"duplicate": 0},
  "user_summary": "ISO List 讀到 0 筆,通常是 sheet 或欄位選錯。",
  "developer": {
    "failed_action": "plan",
    "exception": "ValueError: ISO List 沒有有效資料。",
    "stack": "Traceback (most recent call last): ...",
    "python": "3.12.x","platform": "Windows-10","env": {"PROJECT_ROOT": "..."}
  },
  "suggested_actions": [
    {"id": "open_engineer_mapping","label": "到調校改 Sheet/欄位"},
    {"id": "reselect_iso","label": "重選 ISO List"},
    {"id": "export_bundle","label": "匯出問題包給工程師"}
  ],
  "replay": { "action": "plan", "request": { /* 同 input,可直接丟回 run_iso_workflow */ } },
  "artifacts": {                            // debug bundle 會打包這些
    "events_jsonl": "events.jsonl",
    "plan_csv": "iso_rename_plan_*.csv",
    "preview_pngs": ["preview/p05_serial.png","preview/p05_drawing.png"],
    "job_json": "job.json"
  }
}
```

```jsonc
// .runtime/runs/iso/<run_id>/events.jsonl  （逐事件,append-only）
{"ts":"...","stage":"split","level":"ready","code":"PDF02","msg":"已拆成 18 頁"}
{"ts":"...","stage":"iso","level":"blocked","code":"E003","msg":"ISO List 沒有有效資料。"}
```

並維護一個索引讓 Run Log 抽屜 O(1) 列出:`.runtime/runs/iso/index.json`(最近 50 筆 `{run_id,created_at,mode,status,failed_stage,user_summary}`,LRU)。

### 4.3 欄位責任分層(對應需求清單)

| 需求欄位 | schema 位置 |
| --- | --- |
| run_id / timestamp | `run_id` / `created_at` / `ended_at` |
| input paths | `input.*` |
| selected profile | `profile.*` |
| ROI settings | `input.serial_region` / `input.drawing_region` |
| ISO list parse result | `iso_parse.*` |
| detected rows | `summary` / `counts` / `job.json`(rows) |
| ready/warn/blocked counts | `summary` |
| failed stage | `failed_stage` |
| exception stack | `developer.exception` / `developer.stack` |
| user-facing summary | `user_summary` |
| developer diagnostic | `developer.*` + `pilot[]` |
| suggested next actions | `suggested_actions[]` |
| replay command / payload | `replay`(直接可丟回 `run_iso_workflow`) |
| exportable debug bundle | `artifacts.*` + §4.4 |

### 4.4 Debug Bundle(問題包)

新增 action `export_debug_bundle`:把 `.runtime/runs/iso/<run_id>/` 打包成 `iso_debug_<run_id>.zip`,內含:
- `run.json` + `events.jsonl`
- `plan.csv`(`export_plan_csv` 產物)
- `preview/`(失敗/低信心頁的 serial+drawing 裁切 PNG,**不含整份 PDF**,避免外洩與肥大;可選「含整頁縮圖」)
- `pilot.json`(完整 PilotReport)
- `env.txt`(python/平台/套件版本:pypdf、opencv、rapidocr)
- **不放**:原始 PDF、ISO xlsx(預設只放路徑與 sha1;勾選才打包,避免機密外流)。

### 4.5 Replay(還原現場)

- 「調校 > Run Log > 某筆 > Replay」:把 `replay.request` 丟回對應 action,**先進 dry-run / 不自動 apply**;狀態機進 `replaying`(§6)。
- Replay 不覆蓋目前 profile;ROI/欄位以 run log 的值載入到「草稿層」(§5.4),工程師確認後才另存。
- 對應測試:`test_iso_run_log.py`(round-trip + replay 還原相同 summary)。

---

## 5. ROI / 調校設計

ROI 是「離不開舊版的主因」(見 gap 文件 P0-1)。現況:調校頁有 serial/drawing **滑桿** + 重設,但**無拖框 overlay、無多頁採樣、無 heatmap、無 preset、無 revert,且調完直接寫進該資料夾 profile(=污染)**。

### 5.1 兩個 ROI 的調法(serial / drawing 一致流程)

1. 右欄選 `流水號 ROI` 或 `圖號 ROI`(已存在 `activeRoi`)。
2. 在整頁 PDF 預覽上**直接拖框**(新增 React `RoiOverlay`,對應舊版 `region_selector.py`);拖完即時更新 `serialRegion/drawingRegion`(normalized 0–1)。
3. 滑桿與座標數字(LEFT/TOP/WIDTH/HEIGHT)與拖框**雙向綁定**(滑桿仍保留給精修)。
4. 放開即用目前頁重判(`preview_iso_pdf_page` 已支援 `serial_region/drawing_region`),右側顯示裁切圖 + 讀數 + 信心。

### 5.2 Overlay / 多頁採樣 / Heatmap(都要)

- **Overlay preview(要)**:在整頁上畫半透明框 + 角落把手;serial 框與 drawing 框用兩色。這是把「滑桿盲調」變「看著圖調」的關鍵。
- **多頁採樣(要)**:加「取樣 N 頁(預設 5,跨前/中/後)」按鈕,對同一 ROI 在多頁判讀,回傳每頁信心。解決「第一頁剛好對、其它頁偏掉」。對應 pilot P08。
- **Confidence heatmap(要,輕量版)**:不做像素級熱力圖(太重);改成**取樣頁的信心長條 + 偏移建議**(例如「右移 0.02 可從 0.61 → 0.88」),由二階段自動校準(找「流水號」label)算出建議框,一鍵採用。

### 5.3 Profile presets / per-project profile

- **Per-project profile(已有雛形)**:現在依資料夾存 `IsoNamingProfile`。保留,但 schema 升級(§5.5)。
- **Presets(新增)**:把常見圖框存成具名 preset(`F3-Vendor-A` 之類),存 `.runtime/iso_profiles/presets/<id>.json`;調校頁可「套用 preset → 微調 → 另存」。
- **自動推薦(未來)**:對第一頁圖框做 perceptual hash,與 preset 的 `frame_hash` 比對,命中就建議(next_stage §6.4)。本計畫先留欄位,不強制做。

### 5.4 不污染一鍵預設值(草稿層 vs 已發布層)— 關鍵安全設計

把 profile 分兩層,避免「工程師在調校亂拖框 → 長官的一鍵跟著壞」:

| 層 | 存放 | 誰用 | 寫入時機 |
| --- | --- | --- | --- |
| **published(已發布)** | `state_store` 的 `iso_naming_profile(folder)`(現況) | 一鍵 + 工作台讀這層 | 只有按「發布 profile」才寫 |
| **draft(草稿)** | 記憶體 + `.runtime/runs/.../draft_profile.json` | 調校頁當前編輯 | 拖框/改門檻即時寫 draft,不動 published |

- 調校頁頂端顯示 chip:`Profile:已發布 v3 · 草稿有未發布變更`。
- 一鍵與工作台**永遠讀 published**;調校的 draft 不影響它們,直到工程師明確「發布」。
- 「發布」= modal 二次確認 + 寫 published + 記一筆 run log(profile_published 事件)。
- 目前 `generatePlan()` 會自動 `saveIsoProfile(...)` → 要改成**只存 draft**,把「寫 published」收斂到明確發布動作(這條是現在會悄悄污染的點,需修)。

### 5.5 Profile schema 升級(`profile.py` 加版本)

```python
@dataclass(frozen=True)
class IsoNamingProfile:
    schema_version: int = 2        # 新增;1→2 migration
    serial_region: SerialVisionRegion = DEFAULT_SERIAL_REGION
    drawing_region: SerialVisionRegion = DEFAULT_DRAWING_REGION
    confidence_threshold: float = 0.70
    pattern: str = "{serial}--{line}.pdf"
    iso_list_path: Path | None = None
    sheet_name: str | None = None
    serial_col: int | None = None
    line_col: int | None = None
    # 新增:
    preset_id: str | None = None        # 來自哪個 preset
    frame_hash: str | None = None       # 圖框 perceptual hash(未來自動推薦)
    updated_at: str | None = None
    updated_by: str | None = None       # 稽核:誰發布的
    history: tuple[dict, ...] = ()       # 最近 5 版 published 快照,供 revert
```

### 5.6 回復上一版(revert)

- published 每次發布前,把舊值 push 進 `history`(保留 5 版)。
- 調校頁「Profile」區加 `回復上一版`:從 `history[-1]` 還原 + 記 run log。
- draft 隨時可「丟棄草稿 → 回到 published」。
- 對應測試:`test_iso_profile.py` 補 migration(v1→v2)、history 上限、revert round-trip。

---

## 6. 工作台狀態與操作流程(狀態機)

目前 `oneClickStage` 只涵蓋一鍵(idle/running/applying/review/done)。工作台與調校沒有明確狀態機,按鈕 enable/disable 散在各處 → 這是「不穩」的第二個根因。建議抽一個**統一狀態機**(前端 `useIsoMachine` hook + 後端不需改),三視圖共用。

### 6.1 狀態定義 + 每態 UI / 可按 / 禁用 / 下一步 / 回安全

| 狀態 | UI 顯示 | 可按 | 禁用 | 下一步 | 回安全狀態 |
| --- | --- | --- | --- | --- | --- |
| `waiting` | 來源未齊;主按鈕「選擇工作資料夾」 | 選來源、切視圖 | 產生草稿、套用、批次判讀 | 選到來源 → `input_ready` | 已是安全態 |
| `input_ready` | 來源/ISO 摘要 chip 綠;主按鈕「產生命名草稿」/「開始一鍵命名」 | 產生草稿、批次判讀、調 ROI(調校) | 套用 | 產生 → `draft_generating` | 回 `waiting`(清來源) |
| `draft_generating` | pipeline 跑動;主按鈕「處理中…」+ 可取消 | 取消 | 套用、改設定 | 完成 → `draft_ready`/`warn`/`blocked`;例外 → `failed` | 取消 → `input_ready` |
| `draft_ready` | 命名表全綠;指標 blocked=0,warn=0 | 套用、逐列改、匯出 CSV | — | 套用 → `ready_to_apply`→`applying` | 已安全 |
| `warn` | 有 warn 列(黃);主按鈕「我已確認,更名 N 筆」需勾確認 | 採用判讀/確認列/改值、套用(勾確認後) | 直接套用(未勾) | 全部確認 → `draft_ready`;套用 → `applying` | 回 `draft_ready` |
| `blocked` | 有 blocked 列(紅);主按鈕「前往工作台修正 N 筆」 | 逐列修、改欄位/ROI(調校) | 套用 blocked 列 | 修到 0 → `warn`/`draft_ready` | 留在 blocked(安全) |
| `manual_review` | 工作台逐列校對中(選取某列) | 採用判讀、確認列、改 serial/line/new_name、下一個問題 | 套用整批(可套單列) | 問題清空 → `draft_ready` | 回 `draft_ready` |
| `ready_to_apply` | dry-run 對話框(逐筆 src→dst + risk) | 確認套用、匯出計畫、取消 | — | 確認 → `applying` | 取消 → 回前一態 |
| `applying` | 進度;原子批次 | (不可中斷) | 全部 | 成功 → `applied`;部分失敗 → `failed`(可回復) | 完成後才動 |
| `applied` | 結果頁:成功/警告/阻擋 + 記錄路徑 | 撤銷此批、匯出、再處理一批 | — | 再處理 → `waiting` | 已安全 |
| `failed` | 失敗卡(§7):user_summary + 三顆鈕 | 交給工程師、匯出問題包、開啟調校、重試 | 套用 | 重試 → `draft_generating`;救援 → `replaying` | 一律可回 `input_ready` |
| `replaying` | 用 run log replay,**強制 dry-run**,不自動 apply | 看差異、調 ROI/欄位、另存 profile | 自動 apply | dry-run 過 → `ready_to_apply` | 取消 → `input_ready` |
| `tuning` | 調校編輯 ROI/門檻/欄位(draft 層) | 拖框、多頁採樣、發布 profile、回復上一版 | 寫 published(除非按發布) | 發布 → 回原視圖;重跑 → `draft_generating` | 丟棄草稿 → published |

### 6.2 轉換守則

- **狀態只能經 `useIsoMachine.transition(event)` 改**,UI 不直接 `setDisabled`(對齊 next_stage §3.2:UI 不准直接 setText/setEnabled)。
- **`applying` 不可取消**(原子批次);其餘狀態皆可回安全態。
- **每次進入 `failed` 一定先寫完整 run log**(§4),否則救援無資料。
- **危險轉換需閘門**:`warn → applying` 需勾「我已確認」;`tuning → 發布` 需 modal;`applied → 撤銷` 需確認。
- 一鍵視圖只暴露 `waiting/input_ready/draft_generating/warn/blocked/applying/applied/failed` 的「精簡版」(沿用現有 `oneClickStage` 映射);工作台/調校暴露全集。

### 6.3 與現有碼的對接

- `oneClickStage` 維持(一鍵用),但改成 `useIsoMachine` 的投影:`idle→waiting/input_ready`、`running→draft_generating`、`review→warn/blocked`、`applying→applying`、`done→applied`。
- `batchJob.state`(queued/running/cancelled/completed/failed)維持,作為 `draft_generating` 的子進度來源。
- 新增的 `replaying / tuning` 只在工作台/調校出現,不污染一鍵。

---

## 7. 一鍵失敗後的導流

原則:**一般使用者看到「人話 + 三個選擇」,工程師拿到「可還原的 run_id」。**

### 7.1 一般使用者看到的(一鍵失敗卡)

一鍵失敗時,event log 末尾出現一張卡(不是 stack trace、不是紅字噴錯):

```
┌ 這批沒有完成 ────────────────────────────────────────────┐
│ ⚠ ISO List 讀到 0 筆,通常是 sheet 或欄位選錯。            │   ← user_summary(來自 run log)
│                                                          │
│ 已保留現場(編號 iso-20260608-143312-3f9a)                │   ← run_id,給工程師報修用
│                                                          │
│ [ 交給工程師 ]   [ 匯出問題包 ]   [ 開啟調校工作台 ]      │
└──────────────────────────────────────────────────────────┘
```

- **不顯示**:exception、stack、檔案路徑全文、欄位 index。這些在 run log 裡,工程師才看。
- `user_summary` 由 `failed_stage` 對應一句人話模板(iso→「sheet/欄位選錯」、source→「PDF 打不開或被佔用」、detect→「判讀信心太低」…)。

### 7.2 三顆鈕行為

| 鈕 | 行為 |
| --- | --- |
| **交給工程師** | 複製 `run_id` + user_summary 到剪貼簿(可選:開預設信件草稿);提示「把這段貼給工程師即可」。**不需要使用者懂任何細節。** |
| **匯出問題包** | 呼叫 `export_debug_bundle`(§4.4),存出 `iso_debug_<run_id>.zip`,並用 `present_files` 等同機制讓使用者拿到檔。 |
| **開啟調校工作台** | 切 `isoView="engineer"` 並自動 `replay` 該 `run_id` → 進 `replaying` 狀態,左側 Pilot List 自動跳到 `failed_stage` 紅項。 |

### 7.3 工程師打開工作台後(還原現場)

1. 「調校 > Run Log 抽屜」預設選中最近一筆 failed run(或由失敗卡帶入的 `run_id`)。
2. 載入 `run.json`:輸入快照、profile、ROI、ISO parse 結果、pilot、stack 全部回填到**草稿層**(不動 published)。
3. Pilot List 自動定位 `failed_stage`(例如 P04/P05 紅),點開看 `engineer_detail`(sheet 分數、headers、樣本值)。
4. 工程師調 Sheet/欄位/ROI → 按「Replay(dry-run)」→ 看 summary 是否轉綠 → 滿意才「發布 profile」+ 正常套用。
5. 全程不需重問使用者任何輸入(因為 run log 全存了)。

### 7.4 需要的新東西小結

- 失敗卡元件(一鍵 + 工作台共用)。
- `export_debug_bundle` action。
- `replay` 進入點(失敗卡鈕 + Run Log 抽屜)。
- run log 落地(§4)——**這是前置依賴,要先做**。

---

## 8. 測試策略(測試矩陣)

沿用現有 `tests/`(已有 `test_tauri_iso_workflow.py`、`test_iso_one_click_workflow.py`、`test_iso_validator.py`、`test_iso_profile.py`、`test_serial_vision.py`、`test_preview_cache.py`、`test_iso_review_filter.py`、`test_tauri_iso_preview.py`、`test_batch_detect_thread.py`…)。下表為**要補的**矩陣。

| # | 情境 | 層級 | 新增/擴充測試 | 驗收重點 |
| --- | --- | --- | --- | --- |
| T01 | 一鍵 happy path(全綠一路到底) | 後端整合 | 擴 `test_iso_one_click_workflow.py` | plan→batch→apply 全綠,summary.selected==renamed_count |
| T02 | 一鍵失敗但能產生 run log | 後端 | 新 `test_iso_run_log.py` | 失敗(ISO 0 筆)→ run.json 有 failed_stage="iso"、user_summary、replay、stack |
| T03 | 工作台讀 log 還原 | 後端 | `test_iso_run_log.py` | 由 run_id 載回 input/profile/ROI,值與寫入一致 |
| T04 | ROI 調整後重新產生 draft | 後端 | 擴 `test_tauri_iso_workflow.py` | 改 serial_region → 重判信心/text 改變;published 不被改 |
| T05 | blocked rows 人工修正 | 前端邏輯 | 新 `test_iso_machine.ts`(vitest)或 `test_iso_review_filter.py` | updateRow/confirmSelectedRow 後 status: blocked→ready |
| T06 | dry-run | 後端 | 擴 `test_iso_rename_plan.py` | 逐筆 risk 標示;存在/重複/非法字元被攔 |
| T07 | rollback / undo | 後端 | 新 `test_iso_undo.py` | apply 後反向 rename 還原檔名;undo 寫入失敗→E008 |
| T08 | profile save/load + draft/published 分層 | 後端 | 擴 `test_iso_profile.py` | draft 改不動 published;發布才寫;revert 還原 history |
| T09 | malformed ISO list | 後端 | 擴 `test_iso_naming.py` | 壞 xlsx/空 sheet/缺欄 → blocked + 對應 issue 碼,不 crash |
| T10 | missing pages(combine 壞/0 頁) | 後端 | `test_tauri_iso_workflow.py` | P02/P03 blocked,user_summary 清楚 |
| T11 | duplicate serial | 後端 | 擴 `test_iso_rename_plan.py` | 兩頁同號→重複偵測 blocked / 加後綴策略 |
| T12 | OCR confidence low | 後端 | 擴 `test_serial_vision.py` | 低於門檻→warn + 暫用頁序;多頁採樣信心分布 |
| T13 | 路徑含中文字 | 後端 | 新 `test_iso_paths_cjk.py` | 中文資料夾/檔名全程 ok(stdio utf-8、CSV utf-8-sig、zip 名) |
| T14 | Windows 檔案被鎖 | 後端 | `test_rename_actions.py` 擴 | 來源被佔用→E006,提示關閉程式,不部分更名 |
| T15 | Tauri 原生 vs 瀏覽器 fallback | 前端 | 擴 `App.tsx` 對 `isTauri()` 分支 | 非 Tauri:pick/preview 給友善訊息,不白屏 |
| T16 | replay 還原 | 後端 | `test_iso_run_log.py` | replay.request 丟回 action → 與原 run summary 一致 |
| T17 | debug bundle | 後端 | 新 `test_iso_debug_bundle.py` | zip 含 run.json/events/csv/pilot/env;預設不含原始 PDF/xlsx |
| T18 | Pilot report 17 項 | 後端 | 新 `test_iso_pilot.py` | 各 stage 的 ready/warn/blocked 條件;與 validator 7 閘門相容 |
| T19 | 狀態機合法/非法轉換 | 前端 | `test_iso_machine.ts` | 12 態合法轉換通過;`applying` 不可取消;非法轉換被擋 |
| T20 | 一鍵畫面保護(回歸) | 前端 | 新 `test_autopilot_guard.ts` | autopilot 視圖 DOM 不含 ROI/欄位/門檻/舊版鈕(防止工程資訊滲入) |

測試節奏:每個 task 後跑 `python -m pytest tests/`(後端)與前端 vitest;CI 至少跑 T01/T02/T03/T09/T13/T20(最能擋回歸的六條)。

---

## 9. 建議模組 / 檔案結構

原則:(1) 前端把 3051 行 `App.tsx` 依三視圖拆開;(2) 後端 ISO 邏輯**不依賴 PyQt**(批次 worker 才碰 Qt);(3) run log / pilot 各自獨立可測。

### 9.1 前端(`frontend/tauri-spike/src/`)

```
src/
├── App.tsx                        # 只留殼:dock/cockpit + 導覽,移除 ISO 巨component
├── iso/
│   ├── IsoBoard.tsx               # ISO 頁外殼:三視圖切換 + 共用 state（由 useIsoWorkflow 提供）
│   ├── AutopilotView.tsx          # 一鍵(只讀 pipeline + 主按鈕 + event log + 失敗卡)
│   ├── WorkbenchView.tsx          # 工作台(設定軌 + 命名表 + PDF 校對)
│   ├── EngineerView.tsx           # 調校(ISO 對映 + Job protocol + ROI 編輯 + Profile 發布)
│   ├── components/
│   │   ├── PipelineSteps.tsx      # 6 格 stepper(共用)
│   │   ├── OneClickButton.tsx     # 7 種語意主按鈕(共用)
│   │   ├── NamingTable.tsx        # 命名表 + 5 類分色 + 信心欄排序
│   │   ├── IsoVisualPanel.tsx     # 已存在,抽出來;PDF 預覽 + 裁切
│   │   ├── RoiOverlay.tsx         # 新:整頁拖框 overlay(對應舊 region_selector)
│   │   ├── RoiSamplePanel.tsx     # 新:多頁採樣 + 信心長條 + 偏移建議
│   │   ├── PilotListDrawer.tsx    # 新:17 項 pilot 抽屜
│   │   ├── RunLogDrawer.tsx       # 新:run 歷史 + 時間軸 + replay/匯出
│   │   ├── FailureCard.tsx        # 新:一鍵失敗卡(§7)
│   │   ├── ProfilePublishModal.tsx# 新:draft→published 發布/diff/revert
│   │   └── EventLog.tsx           # 只讀事件流
│   └── hooks/
│       ├── useIsoWorkflow.ts      # 來源/ISO/plan/preview 狀態 + invoke 封裝
│       ├── useIsoMachine.ts       # §6 狀態機(transition/guard)
│       ├── useBatchJob.ts         # 批次 job 輪詢(由現有 useEffect 抽出)
│       ├── useRoiTuning.ts        # draft ROI / 多頁採樣 / revert
│       └── useRunLog.ts           # run 列表 / 載入 / replay
├── isoWorkflow.ts                 # 既有型別 + invoke;補 pilot_report/export_debug_bundle/undo 型別
├── legacy.ts                      # 既有舊版橋接(移到 developer-only)
└── styles.css                     # 既有
```

### 9.2 後端(`launcher/`)

```
launcher/
├── app/
│   ├── tauri_iso_workflow.py      # 既有;新增 action:pilot_report / export_debug_bundle / undo_batch / save_draft_profile / publish_profile
│   ├── tauri_iso_worker.py        # 既有批次 worker;改成同時 append run log events.jsonl
│   └── tauri_iso_preview.py       # 既有
├── plugins/iso_tools/
│   ├── iso_naming.py serial_vision.py serial_correction.py rename_plan.py   # 既有
│   ├── issues.py validator.py     # 既有;validator 擴成 pilot 子集
│   ├── profile.py                 # 既有;升 schema v2 + draft/published + history(§5.5)
│   ├── pilot.py                   # 新:PilotItem/PilotReport + build_pilot_report()
│   ├── run_log.py                 # 新:RunLog 寫入/讀取/索引/replay payload
│   ├── debug_bundle.py            # 新:打包 zip(§4.4)
│   └── undo_log.py                # 新:套用記錄 + 反向 rename(SQLite 或 JSONL)
├── ui/iso_pdf/                    # 舊版 PyQt 保留(legacy/對照/測試)——不動、不拔
└── core/
    ├── state_store.py             # 既有;profile published 仍走這
    └── paths.py                   # 既有;新增 runs_root() / presets_root()
```

### 9.3 Schema / fixtures / docs

```
schemas/                          # 建議新增,給前後端共用對照(JSON Schema)
├── iso_run_log.schema.json
├── iso_pilot_report.schema.json
└── iso_profile_v2.schema.json

tests/fixtures/iso/               # 取樣 fixtures
├── good_combine.pdf  good_iso_list.xlsx          # happy path
├── malformed_iso_empty.xlsx  malformed_iso_no_serial.xlsx
├── duplicate_serial_iso.xlsx
├── cjk_中文資料夾/中文_combine.pdf  中文_iso.xlsx  # 中文路徑
└── low_conf_pages/                               # 低信心頁

docs/
├── iso_pdf_workbench_pilot_plan_v0.1.md          # 本文
└── (既有藍圖/audit/next_stage/gap 文件)
```

---

## 10. 優先級

> 節奏:一週 ≈ 工程師 8–10 小時;每階段結束都要可 demo + 可回歸。

### 10.1 現在就該做(P0:補失敗復原地基,不動一鍵 UI)

1. **run log 落地**(`run_log.py` + `.runtime/runs/iso/`):plan/一鍵/batch/apply 都開一筆 run,失敗一定寫 `failed_stage/user_summary/stack/replay`。(T02/T03)
2. **一鍵失敗卡 + 三顆鈕**(`FailureCard.tsx`):交給工程師(複製 run_id)、匯出問題包、開啟調校。**只動失敗時的 event log 末端,不改一鍵正常流程。**(T20 確保不滲入)
3. **`export_debug_bundle` action + `debug_bundle.py`**。(T17)
4. **profile draft/published 分層**(§5.4):把 `generatePlan()` 的自動 `saveIsoProfile` 改成只存 draft,止住「悄悄污染一鍵」。(T08)

### 10.2 一鍵更穩後做(P1:工作台校對體驗 + Pilot List)

5. **Pilot List 17 項**(`pilot.py` + `PilotListDrawer.tsx`),validator 擴為其子集。(T18)
6. **Run Log 抽屜 + Replay**(`RunLogDrawer.tsx` + `replay`),失敗卡「開啟調校」自動 replay。(T16)
7. **命名表 5 類分色 + 信心欄排序 + 「下一個問題」循環**。(T05)
8. **ROI 拖框 overlay**(`RoiOverlay.tsx`,對應舊 `region_selector`)。(T04)

### 10.3 工作台大改版時做(P2:狀態機 + god component 拆解 + 調校安全)

9. **抽 `useIsoMachine`**(§6 十二態),三視圖共用,UI 不再各自 setDisabled。(T19)
10. **拆 `App.tsx`**:`IsoBoard / AutopilotView / WorkbenchView / EngineerView` + hooks(§9.1),目標單檔 < 500 行。
11. **ROI 多頁採樣 + 偏移建議**(`RoiSamplePanel.tsx`)、**profile presets + revert**(§5.3/5.6)。
12. **profile schema v2 migration + history**。(T08)
13. **undo/rollback**(`undo_log.py` + `undo_batch` action)。(T07)

### 10.4 等要正式包 exe 前做(P3:穩定度 / 收尾 / 下架準備)

14. **中文路徑 / 鎖檔 / 瀏覽器 fallback 全測**(T13/T14/T15)。
15. **效能基準**:預覽/批次的冷啟與每頁耗時記在 audit 附錄;確認 lazy import(opencv/rapidocr 只在 worker 載)。
16. **舊版橋接退到 developer-only**(過渡;**不拔 PyQt6**,只從工作台主動線移除)。
17. **CI 跑回歸六條**(T01/T02/T03/T09/T13/T20),打包前綠燈才出 exe。
18. **debug bundle 隱私確認**:預設不含原始 PDF/xlsx,只放路徑 + sha1。

---

## 附錄 A — 可直接交給 Codex 的任務(對齊 `codex_指令書…` 格式)

> 每個任務標 **可改檔 / 不准動 / 驗收**;先做 A1(run log)因為失敗卡與 replay 都依賴它。

**A1 — run log 落地(P0,前置)**
- 可改/新增:`launcher/plugins/iso_tools/run_log.py`、`launcher/app/tauri_iso_workflow.py`(各 action 包一層 run 記錄)、`launcher/app/tauri_iso_worker.py`(append events.jsonl)。
- 不准動:`App.tsx` 的一鍵正常流程、`iso_pdf_naming_dialog.py`。
- 驗收:`tests/test_iso_run_log.py`:失敗(ISO 0 筆)寫出 run.json,含 `failed_stage/user_summary/replay/developer.stack`;happy path status=="completed"。

**A2 — 一鍵失敗卡 + 三顆鈕(P0)**
- 可改/新增:`src/iso/components/FailureCard.tsx`、在 `AutopilotView` 失敗時掛上。
- 不准動:一鍵正常 pipeline/主按鈕語意。
- 驗收:`test_autopilot_guard.ts`(autopilot DOM 無 ROI/欄位/門檻/舊版鈕);失敗卡顯示 user_summary + run_id,三鈕可點。

**A3 — export_debug_bundle(P0)**
- 可改/新增:`iso_tools/debug_bundle.py`、`tauri_iso_workflow.py` action、`isoWorkflow.ts` 型別。
- 驗收:`test_iso_debug_bundle.py`:zip 含 run.json/events/csv/pilot/env;預設不含原始 PDF/xlsx。

**A4 — profile draft/published 分層(P0)**
- 可改:`profile.py`、`tauri_iso_workflow.py`(`save_profile`→分 `save_draft_profile`/`publish_profile`)、`App.tsx`(`generatePlan` 改存 draft)。
- 驗收:`test_iso_profile.py`:draft 不動 published;發布才寫;一鍵讀 published 不受調校影響。

**A5 — Pilot List 17 項(P1)**
- 可改/新增:`iso_tools/pilot.py`、`tauri_iso_workflow.py` `pilot_report` action、`src/iso/components/PilotListDrawer.tsx`。
- 不准動:`validator.py` 既有 7 閘門簽名(要相容)。
- 驗收:`test_iso_pilot.py` 涵蓋各 stage 三態;validator 7 閘門為 pilot 子集。

**A6 — useIsoMachine 狀態機(P2)**
- 可改/新增:`src/iso/hooks/useIsoMachine.ts`,三視圖接上。
- 驗收:`test_iso_machine.ts`:12 態合法轉換;`applying` 不可取消;非法轉換被擋。

## 附錄 B — 刻意不做 / 風險提醒

- ❌ **不拔 PyQt6**:舊版是 legacy/對照/測試與「新圖框暫時救援」的後路;只把橋接退到 developer-only。
- ❌ **不為一鍵寫第二條 pipeline**:三視圖共用 `run_iso_workflow` + 同一 plan;失敗卡/replay 也走同協定。
- ❌ **不在一鍵畫面加任何工程資訊**:ROI/欄位/門檻/RunLog/JSON 一律不得出現(T20 守門)。
- ❌ **不讓調校污染一鍵**:draft/published 分層是硬規則;`generatePlan` 不准再自動寫 published。
- ❌ **debug bundle 不打包原始機密檔**:預設只放路徑 + sha1,勾選才含,避免 ISO/PDF 外流。
- ❌ **批次/replay 不用一次性子程序假裝串流**:沿用現有 `job.json` 檔案串流(已可回報 progress/events)。
- ⚠ **run log 會長大**:用 `index.json` LRU 50 筆 + 定期清 `.runtime/runs/iso/`;debug bundle 匯出後可刪原始 run 目錄。

---

> 建議第一步:**A1(run log 落地)**。它範圍小、當天可驗,且失敗卡、replay、Pilot List、debug bundle 全都依賴它——投資報酬最高,也直接把「一鍵失敗 → 工作台救援」這條斷鏈接起來。
