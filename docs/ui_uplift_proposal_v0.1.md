# UI 強化設計提案 v0.1
## Dock 工具列 / Command Palette / Job Monitor

> 範圍:`launcher/ui/dock_window.py`、`launcher/ui/command_palette.py`、`launcher/ui/job_monitor.py`、`launcher/ui/theme.py`
> 痛點優先順序:**①色彩字型間距老氣 → ②警示/狀態高亮不夠 → ③排版擁擠按鈕太多**
> 視覺原型:`docs/ui_uplift_mockup.html`(雙擊用瀏覽器開,左右對比)
> 限制:維持 PyQt6 + QSS,不引入外部依賴(qtawesome 可選但非必要)

---

## 0. 我為什麼判斷它「醜」

不是主觀感受。對照三個視窗的現況,具體有六個工程上的問題:

1. **配色冷且工程藍**:`#eef4f8` panel + `#1f6feb` accent + `#b5c7d6` border。整體偏冷藍灰,現代 desktop UI 的潮流是「暖中性 + 飽和重點色」(VS Code、Linear、Raycast 全往這個方向走)。
2. **缺乏 contrast hierarchy**:GroupBox 邊框、按鈕邊框、表格邊框都用相近的灰藍 1px,**沒有 elevation 層次**(沒有 shadow、沒有 surface 區別)。
3. **字型尺寸只有一階**:13 px 全部通吃,沒有 H1/H2/body/caption 的 type scale。
4. **狀態色用得太克制**:`success_bg=#e7f6ef` + `success=#166534` 飽和度太低,在白底上幾乎看不出來;`danger_bg=#ffe9e6` + `danger=#8a1f17` 也不夠搶眼。
5. **Dock 水平模式 8–10 顆同樣大小的 QToolButton 排成一條**:沒有「主要動作 vs 次要動作」的視覺分群。
6. **Tail 模式是純藍方塊**:`#1f6feb` 130×16 不帶任何資訊。應該至少帶一個 context 狀態色點,像 macOS menubar item。

---

## 1. 設計原則(全文引用基準)

1. **Density-friendly, not density-numb.**
   Dock 是常駐工具列,不能變寬鬆;但密度高 ≠ 元件擠。**用 spacing scale 與 size hierarchy 做出主次**,而不是讓每個按鈕都同樣大。

2. **Status without reading.**
   使用者餘光掃過去就要能判斷「這列要看 / 這個動作完成了」。**色票語意化**(success/warning/danger/info 各自有 fg + bg),並且**強度比現在強一倍**。

3. **Discoverability ≥ Memorability.**
   使用者開夠多次就會記住快捷鍵,但**第一週要靠視覺**。鍵盤提示(`⌘K`、`Ctrl+1`)要常駐顯示在 hover/blur 兩態。

4. **No emoji, no gradient, no cute illustration.**
   工程工具不要可愛;但**接受一點 motion**(120 ms 的色彩 transition、200 ms 的 menu fade)。Qt 對 QSS transition 支援有限,但 hover 色階變化必做。

5. **One source of truth.**
   所有顏色從 `theme.py` 出。三個視窗的 QSS 都吃同一套 token。

---

## 2. Design Tokens

### 2.1 色彩(兩個方案,二選一)

**Theme A — Graphite(推薦):中性灰底 + 靛藍重點**

> 適合工程工具,能避開「Win9x 藍」的觀感;狀態色飽和度足夠。

| Token | 值 | 用途 |
| - | - | - |
| `bg.app` | `#f5f6f8` | 視窗底色 |
| `bg.surface` | `#ffffff` | 卡片 / 面板 |
| `bg.surfaceAlt` | `#f0f2f5` | 次層卡片 / 偶數列 |
| `bg.subtle` | `#e7eaee` | 工具列分隔背景 |
| `text.primary` | `#0c1320` | 主要文字 |
| `text.secondary` | `#3f4855` | 次要文字 |
| `text.muted` | `#6b7280` | 提示 / 描述 |
| `text.inverse` | `#ffffff` | 深底文字 |
| `border.subtle` | `#e3e6ea` | 容器邊界(替換現有 `#c8d4df`) |
| `border.default` | `#cbd0d6` | 一般輸入框邊 |
| `border.strong` | `#9aa0a8` | focus / hover 邊 |
| `accent.primary` | `#4f46e5` | 主要 CTA(從藍改靛) |
| `accent.primaryHover` | `#4338ca` | hover |
| `accent.primarySoft` | `#e0e7ff` | 輕量背景 / chip |
| `accent.primaryFg` | `#312e81` | 軟底上的文字 |
| `success.fg` | `#15803d` | 成功文字 / icon |
| `success.bg` | `#bbf7d0` | 成功底(比現在飽和 +30%) |
| `success.border` | `#86efac` | 成功邊 |
| `warning.fg` | `#b45309` | 警告文字 |
| `warning.bg` | `#fde68a` | 警告底 |
| `warning.border` | `#fcd34d` | 警告邊 |
| `danger.fg` | `#b91c1c` | 失敗文字 |
| `danger.bg` | `#fecaca` | 失敗底 |
| `danger.border` | `#fca5a5` | 失敗邊 |
| `info.fg` | `#1e40af` | 提示文字 |
| `info.bg` | `#dbeafe` | 提示底 |
| `shadow.sm` | `0 1px 2px rgba(15, 23, 42, .06)` | 輸入框 |
| `shadow.md` | `0 4px 12px rgba(15, 23, 42, .08)` | 浮層 / palette |
| `shadow.lg` | `0 12px 32px rgba(15, 23, 42, .14)` | 對話框 |

**Theme B — Engineering Blue 2.0:保留藍但更現代**

> 如果你想保留現有色彩慣性,只是「不那麼 Win9x」。

| Token | 值 | 變化 |
| - | - | - |
| `bg.app` | `#eef2f6` | 從 `#eef4f8` 微暖 |
| `accent.primary` | `#2563eb` | 從 `#1f6feb` 加深加飽和 |
| `accent.primarySoft` | `#dbeafe` | 同 Tailwind blue-100 |
| `border.subtle` | `#dde3ea` | 從 `#c8d4df` 變淡 |
| (其餘同 Theme A) | | |

**建議走 Theme A**。Theme B 是給「不想動太多色彩記憶」的退路。

### 2.2 字型 (Type Scale)

```
font.family   = "Inter Variable", "Segoe UI Variable Text",
                "Microsoft JhengHei UI", "Segoe UI", sans-serif
font.mono     = "JetBrains Mono", "Cascadia Mono", Consolas, monospace
                (Inter 在中文 fallback 後會走 JhengHei,字符寬度匹配比 Segoe UI 好)

text.xs       = 11 px, weight 500   ─ caption / 鍵盤提示
text.sm       = 12 px, weight 500   ─ chip / status
text.base     = 13 px, weight 400   ─ body
text.bodyBold = 13 px, weight 600   ─ 強調 body
text.md       = 14 px, weight 600   ─ 段落標題
text.lg       = 16 px, weight 700   ─ 視窗標題
text.xl       = 18 px, weight 700   ─ Dialog 主標題

行高一律 1.45,monospace 一律 1.4
```

### 2.3 間距 / 圓角 / 動畫

```
space.0   = 0           radius.sm = 4 px
space.1   = 4 px        radius.md = 6 px      ─ 按鈕 / 輸入框
space.2   = 8 px        radius.lg = 10 px     ─ 卡片 / dialog
space.3   = 12 px       radius.full = 999 px  ─ chip / pill
space.4   = 16 px
space.5   = 20 px       motion.fast = 120 ms ease-out
space.6   = 24 px       motion.normal = 200 ms ease-out
space.8   = 32 px
```

---

## 3. 元件系統 (Component patterns)

### 3.1 按鈕

四種 variant + 兩種 size:

| Variant | 用法 | 樣式關鍵 |
| - | - | - |
| **primary** | 每個視窗最多一顆主動作 | `accent.primary` 填滿、白字、`shadow.sm` |
| **secondary** | 一般動作(目前所有按鈕的位置) | `bg.surface` + `border.default`、hover `bg.subtle` |
| **ghost** | 工具列、選單觸發 | 無邊無底、hover 才出 `bg.subtle` |
| **danger** | 刪除 / 取消執行中工作 | `danger.fg` + 邊框 `danger.border` |

| Size | 高度 | padding | 用途 |
| - | - | - | - |
| sm | 26 px | 6 px / 10 px | dock 水平模式 |
| md | 32 px | 8 px / 14 px | dialog 內 |

**對照當前**:現在所有按鈕都是 `setFixedHeight(30)` + `padding 8/8`,且都用 `secondary` 樣式。改完後 dock 上「指令」是 `primary sm`,其他是 `ghost sm`,「⋯ 更多」開出來才是次要選單。

### 3.2 Chip / Pill / Badge

- **Status Chip**:左側 8×8 圓點 + 文字,例如 `● 可更名` / `● 需確認 信心 0.62`,色點吃 `success/warning/danger.fg`,底吃 `bg`。
- **Keyboard Hint Pill**:`Ctrl K` 兩個 token,`bg.subtle` + `border.default`,圓角 4。
- **Count Badge**:小圓圈數字,例如 Tab `錯誤 (2)` 用 `danger.bg + danger.fg`,圓角 full。

### 3.3 狀態指示燈

Dock tail / context label / Job header 都會用到。一致規格:

```
8 px 圓點(大號 12 px,小號 6 px),
顏色從 status 色票挑,
帶 1 px halo (lighter shade),
hover 時 tooltip 顯示完整描述。
```

### 3.4 輸入框 (LineEdit)

```
無 hover 邊變化(避免每次滑過跳動),
focus 時:border 由 default → accent.primary,加 2 px ring,
disabled:bg → subtle,文字 → muted。
```

### 3.5 選單 (QMenu)

```
背景 surface,陰影 shadow.md,
item 高度 28 px (現在 default 約 22 px,中文字會擠),
hover 用 accent.primarySoft,
分隔線 1 px border.subtle 帶 8 px 上下 margin。
```

---

## 4. Dock 工具列 — Redesign

### 4.1 目前的問題(具體)

水平模式按鈕順序:

```
[Tail][工程工具][指令][最近指令][最近檔案][最近資料夾][來源][context label][⤢]
[外掛][位置][關閉]
```

= **10 顆同等視覺權重的按鈕** + 1 個資訊 label。在 1080p 上 dock 會佔螢幕 60–80% 寬度,使用者掃描時找不到「我現在該按什麼」。

### 4.2 提案版

```
水平模式 (40 px 高):

┌─────────────────────────────────────────────────────────────────────┐
│ ☰   ⌘ 指令 ⌘K   ▾ Recent   ◯ Explorer · my-project              ⋯ │
└─────────────────────────────────────────────────────────────────────┘
   ↑      ↑          ↑          ↑                                  ↑
   menu   primary    merged     context chip                       overflow
   icon   action     dropdown   (色點 + 來源 + 路徑壓縮)          (外掛/位置/偏好/關閉)
```

關鍵變化:

| 舊 | 新 | 為什麼 |
| - | - | - |
| 「工程工具」標題 label | ☰ icon button(打開 main menu) | 標題沒人讀,改 affordance |
| 「指令」 secondary 按鈕 | `primary` 按鈕 + 鍵盤提示 pill `⌘K` | 強調這是 launcher 的核心 |
| 最近指令 / 檔案 / 資料夾 三顆 | 合併為 `▾ Recent`,展開有 3 個 tab | 從 3 顆按鈕變 1 顆 |
| 「來源」按鈕 + context label 兩個元件 | 合成一個 **Context Chip**:左側狀態色點(綠=Explorer / 藍=Drop / 橙=Manual / 紅=Empty)+ 來源 tag + 路徑壓縮 + 點開有 menu | 視覺 + 互動合一 |
| 外掛 / 位置 / 關閉 三顆 | 收進 `⋯` overflow | 釋放水平空間 |
| `Tail` 跟其他按鈕並列 | 收合時才出現,展開模式不見 | 互斥 |

**按鈕數量從 10 → 5**(其中 4 顆是常用)。

### 4.3 垂直模式

直立面板把 Context Chip 做成 80×80 卡片在頂部,3 顆主按鈕直排 ICON+TEXT 各 64×56,overflow 收最下面。

### 4.4 Tail 模式重做

```
舊:┌────────────────┐  純藍 130×16
   │   工 具 列     │
   └────────────────┘

新:┌──────────────────────┐  surfaceAlt 底,只有頂端 2 px 的 accent ribbon
   │ ●  工具 ⌘K   3 jobs │  ↑ 色點顯示 context 來源狀態
   └──────────────────────┘  ↑ 顯示快捷鍵 + 進行中 job 數量
```

不再是純藍方塊,變成有資訊的 status bar。

### 4.5 Drop target 視覺

目前 `dropTarget="true"` 改 `bg.drop_bg + 2px border accent`。提案版:**整個 dock 蓋一層 8 px 半透明 accent + dashed border**,並中央顯示「拖放至此設為 context」。視覺強度是現在的 3 倍。

---

## 5. Command Palette — Redesign

### 5.1 目前的問題

- 純單欄列表,看不到 action 細節。
- Group header 是 disabled list item,跟 action item 顏色幾乎一樣。
- Recent 用文字「最近」標示,沒有視覺重量。
- 輸入框 placeholder 太長,會被截斷。

### 5.2 提案版

```
┌──────────────────────────────────────────────────────────────────────┐
│  搜尋指令…                                                  ⌘K       │
│  ──────────────────────────────────────────────────────────────────  │
│  Context · Explorer · my-project · 12 個檔案                         │
│ ╭──────────────────────────────────────┬──────────────────────────╮ │
│ │  ─ Recent ────────────────────────   │                            │ │
│ │  📋 複製檔名        Ctrl+1   [系統]   │  複製檔名                  │ │
│ │  ⌘  PDF 拆頁        Ctrl+2   [PDF]   │                            │ │
│ │                                       │  將選取檔案的檔名(不含    │ │
│ │  ─ PDF 工具 (4) ─────────────────    │  副檔名)複製到剪貼簿。     │ │
│ │  📄 PDF 拆頁        Ctrl+3   [PDF]   │                            │ │
│ │  📄 ISO 命名工作台  Ctrl+4   [PDF]   │  • 上次使用:5 分鐘前       │ │
│ │  📄 PDF 合併        Ctrl+5   [PDF]   │  • 命中條件:  ≥ 1 個檔案   │ │
│ │                                       │                            │ │
│ │  ─ 系統工具 (3) ─────────────────    │  ⏎ 執行    Esc 關閉        │ │
│ │  …                                    │                            │ │
│ ╰──────────────────────────────────────┴──────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────┘
       720 × 480                          
```

關鍵元件:

| 元件 | 說明 |
| - | - |
| 搜尋框 | 變大、focus ring,placeholder 縮成「搜尋指令…」 |
| Context bar | 第二列顯示目前 context,讓使用者意識到結果是 filter 過的 |
| Group header | `surfaceAlt` 底 + caps text + count `(4)`,清楚分群 |
| Item row | icon + title + 鍵盤 pill + category chip |
| Recent | 群組固定在頂端、icon 改用實心、不需要 "最近" 兩字 |
| 預覽欄 | 占 36% 寬,顯示 description / 上次使用 / 命中條件 / 鍵盤提示 |
| Empty state | 「沒有匹配。試試 `pdf` 或 `screenshot`」+ 列出 5 個近期常用 |

### 5.3 互動細節

- **`↑/↓`** 在 list 移動;**`→`** 跳到預覽欄、**`←`** 回 list;**`Tab`** 同 `→`。
- **`Ctrl+1..9`** 直接執行(現在已經有,但要把 hint 顯示到 row 右側,不是 prefix `Ctrl+1  XXX`)。
- **`/`** 觸發 advanced filter:`/cat:pdf` 只看 PDF 類、`/recent` 只看最近。
- **無 match** 時不顯示「沒有匹配的指令」一行,改用大字 + 提示。

---

## 6. Job Monitor — Redesign

### 6.1 目前的問題

- 三個 tab 但沒 count badge,使用者要點進去才知道有沒有錯誤。
- Status label 在左,summary 在右,但成功/失敗的視覺差異只有 background 顏色,不夠搶眼。
- 沒有 elapsed time live timer,使用者不知道跑多久了。
- 沒有 progress bar,使用者不知道進度。
- Log 全部 monospace 沒有 level 區分。

### 6.2 提案版

```
┌──────────────────────────────────────────────────────────────────────┐
│  ⏳  PDF 拆頁                                            00:00:12     │
│  執行中 · 第 8 頁 / 24 頁                                             │
│  ████████░░░░░░░░░░░░░░░░░░░░  33 %                                  │
│                                                                       │
│  ┌── 全部 24 ──┬── 錯誤 ❶ ──┬── 產出 ❸ ────────────────────┐      │
│  │                                                              │      │
│  │  16:42:01  INFO  開始處理 sample-08.pdf                      │      │
│  │  16:42:03  INFO  寫出 sample-08-out.pdf (240 KB)             │      │
│  │  16:42:04  WARN  第 9 頁無內容,跳過                          │      │
│  │  16:42:05  INFO  開始處理 sample-09.pdf                      │      │
│  │                                                              │      │
│  └──────────────────────────────────────────────────────────────┘      │
│                                                                       │
│                              [取消]  [複製紀錄]  [儲存到檔案 ⌘S]      │
└──────────────────────────────────────────────────────────────────────┘
       720 × 480 (執行中) ─── 完成後縮成 540 × 360
```

關鍵元件:

| 元件 | 說明 |
| - | - |
| **Status Hero** | 60 px 高的色帶 + ⏳/✓/✗ 大 icon + 標題 + live elapsed timer(右上),狀態變化時整個 hero 換色 |
| **Sub-status** | 「執行中 · 第 8 頁 / 24 頁」這類細節獨立一列 |
| **Progress bar** | 預設 indeterminate (條紋動畫);worker 回 `progress` 事件時切 determinate |
| **Tab 加 badge** | `❶ ❸` 用 danger / info chip,沒事不顯示 |
| **Log entry** | timestamp(muted) + level chip(INFO/WARN/ERROR/ARTIFACT) + 內容(monospace),整列 hover 高亮 |
| **底部 action bar** | 主動作右下 `儲存到檔案`(完成後)或 `取消`(執行中) |

### 6.3 失敗狀態

```
┌──────────────────────────────────────────────────────────────────────┐
│  ✗  PDF 拆頁 失敗                                       00:00:03     │
│     worker 非正常結束 (exit code 1)                                   │
│  ════════════════════════════════════════════════════════════════    │  ← 紅色實心 ribbon
│                                                                       │
│  ┌── 全部 5 ──┬── ❶ 錯誤 ──┬── 產出 ────────────────────────┐      │
│  │  錯誤訊息直接 highlight 到頂                                │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                       │
│           [複製錯誤]  [打開 log 檔案]  [回報 bug]  [關閉]              │
└──────────────────────────────────────────────────────────────────────┘
```

「錯誤」tab 自動被選中,主要動作切換成「複製錯誤 / 打開 log 檔案」。

---

## 7. 落地計畫

### 7.1 `theme.py` 改動範圍

```python
# 新增 / 取代
@dataclass(frozen=True)
class Theme:
    # ... 既有欄位保留作 alias,新增 token group
    bg_app: str
    bg_surface: str
    bg_surface_alt: str
    bg_subtle: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_inverse: str
    border_subtle: str
    border_default: str
    border_strong: str
    accent_primary: str
    accent_primary_hover: str
    accent_primary_soft: str
    accent_primary_fg: str
    success_fg: str
    success_bg: str
    success_border: str
    warning_fg: str
    warning_bg: str
    warning_border: str
    danger_fg: str
    danger_bg: str
    danger_border: str
    info_fg: str
    info_bg: str
    radius_sm: str = "4px"
    radius_md: str = "6px"
    radius_lg: str = "10px"
    space_1: str = "4px"
    space_2: str = "8px"
    space_3: str = "12px"
    space_4: str = "16px"

GRAPHITE_LIGHT = Theme(...)  # ← Theme A 的所有值

# 既有 dock_stylesheet / palette_stylesheet / job_monitor_stylesheet 改吃新 token
```

**舊 token(text/panel/surface/border/primary 等)留 property 別名一陣子**,讓現有檔案不破。

### 7.2 各檔修改估計

| 檔案 | 變更 | 行數 |
| - | - | - |
| `theme.py` | 換 token + 新 stylesheet 規則 | +200 / -50 |
| `dock_window.py` | Recent 三顆合一 + Context chip + overflow menu + Tail 重做 | +80 / -100 |
| `command_palette.py` | 改兩欄、群組 header 元件、預覽欄 | +200 / -30 |
| `job_monitor.py` | Status hero、progress bar、tab badge、log entry 結構化 | +180 / -60 |
| `preferences_dialog.py` | 加「主題」選項 (Graphite / Engineering 2.0) | +30 |
| `state_store.py` | 新增 `theme_name` 欄位 | +10 |

合計 ~700 行新增,~240 行刪除。**全部不動 plugin、不動 core**。

### 7.3 拆兩個 PR

**PR 1 — Tokens & Theme(可獨立 merge,不改視窗結構)**
- `theme.py` 換 Graphite 色票
- 三個視窗的 stylesheet 重綁 token
- `preferences_dialog.py` 加 theme 切換
- 視覺上立刻變現代,但結構不動,風險最低

**PR 2 — Components & Layout**
- Dock 合併 Recent / Context Chip / overflow / Tail
- Palette 兩欄、群組 header 強化、預覽欄
- JobMonitor Hero / Progress / Badge / Log entry 結構化

PR 1 做完使用者就會明顯感受「不那麼老」;PR 2 做完才完成「不那麼擠」。

---

## 8. 視覺原型

`docs/ui_uplift_mockup.html` 已產生。在瀏覽器打開可看到:

1. **設計 Token 卡片**:色彩、字型、間距、按鈕、chip 全部 1:1。
2. **Dock 對照**:目前(舊)vs 提案(新),水平 / 垂直 / Tail 三狀態。
3. **Palette 對照**:單欄 vs 雙欄 + 群組 header + 預覽。
4. **JobMonitor 對照**:三狀態(執行中 / 成功 / 失敗)的 Hero + Progress + Tab badge。

> 注:HTML mockup 是用瀏覽器 CSS 模擬 Qt widget 樣貌,實際 QSS 渲染會略有差異(主要是字型 antialiasing 與圓角細節),但**色票、間距、層次、互動意圖完全等同**。

---

## 9. 待你確認的決策點

| # | 決策 | 我的建議 |
| - | - | - |
| D1 | Theme A (Graphite) vs Theme B (Engineering Blue 2.0)? | **A**(更現代;B 是退路) |
| D2 | Dock 水平模式按鈕從 10 縮到 5,合併 Recent 三顆 + 收 ⋯ overflow,你同意嗎? | 同意 |
| D3 | Tail 模式從純藍方塊改帶 status dot + job count,但會稍微寬一點(130 → 160)? | 同意 |
| D4 | Command Palette 兩欄(列表 60% + 預覽 40%),預覽欄會用 240 px 額外寬度,你 OK 嗎? | 同意,值得 |
| D5 | JobMonitor 加 progress bar,如果 worker 沒回 progress 事件就用 indeterminate 條紋動畫? | 同意 |
| D6 | 字型主家族要不要採用 Inter Variable(免費可商用,需打包進專案 ~600 KB)? | 不要,目前 Segoe UI Variable + JhengHei 已夠用,Inter 收益 < 包大小成本 |
| D7 | 偏好設定要不要加「主題切換」? | 要,Theme A/B 切換是 PR 1 一起出 |

---

> 你回覆 D1–D7 後,我可以接著直接動手做 PR 1(theme tokens 全換 + 偏好設定加 theme),預估 200 行內可完成,你 git diff 即可確認。
