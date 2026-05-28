# 安全清除工作台 GUI 重新設計 — Codex 指令書 v0.1

> 對照基準：`launcher/ui/safe_cleanup_dialog.py`、`launcher/ui/theme.py`、`launcher/ui/quarantine_browser_dialog.py`、`launcher/core/safe_cleanup.py`
> 適用版本：Engineering Launcher 0.1.x
> 文件用途：交付給 Codex / Claude Code agent 執行的 GUI 改造工作清單。每個區塊都列「目的、檔案異動、關鍵程式碼、驗收條件」。

---

## 0. 通則 — 開工前先讀

### 0.1 設計目標

讓非工程師使用者也能放心使用「安全清除工作台」。三個首要目標：

1. **看得懂**：一眼看出「目標是什麼、影響範圍多大、安不安全」。
2. **不會壞**：所有清除預設仍走隔離區 + manifest，不做永久刪除。
3. **漂亮舒適**：卡片化、寬鬆留白、語意色＋圖示、有質感的過場與 hover。

### 0.2 不可破壞的契約

- `SafeCleanupDialog(context, parent)` 的對外簽章不變。
- `launcher.core.safe_cleanup` 的所有資料類別（`CleanupPlan`、`CleanupPlanItem`、`CleanupApplyResult`、`OfficialUninstaller`、五個 `*_LAYER` 常數）不改。
- 「先隔離、不真刪」這條紅線不能放鬆；任何「一鍵清除」最終仍呼叫 `apply_cleanup_plan(...)`，產出 manifest 與 `Restore-Registry.ps1`。
- HKLM / Windows Installer 殘留仍維持「只列出、不執行」，不能在新版 UI 被一般使用者誤觸。

### 0.3 驗收原則

- 每個區塊完成後，`pytest tests/test_safe_cleanup_dialog.py` 必須通過；如改了行為，同步更新測試。
- 新增的視覺元件（卡片、徽章、tab、CTA）每一個都要有獨立的 QWidget 子類別，便於後續 reuse 與單測。
- 任何字串都走 i18n-ready 寫法（直接寫繁中字串字面值即可，不需要 gettext，但所有顯示文字集中在 dialog 檔案頂部常數區或 `_layer_label()` 一類 helper，避免散落）。
- 在 1280×800 視窗下整個 dialog 不出現水平捲軸；在 1920×1080 下卡片要等比放大、不被拉到視覺鬆散。

---

## 1. 視覺系統升級（Design Tokens）

### 1.1 擴充 `launcher/ui/theme.py`

**目的**：現有 `Theme` 沒有「五個風險層級」、「圓角」、「陰影」、「卡片背景」這些 token，新版需要。

**檔案異動**：`launcher/ui/theme.py`

**新增欄位**（同時補進 `DEFAULT_LIGHT` 與 `ENGINEERING_BLUE_LIGHT`，建議再追加一個 `GRAPHITE_DARK`）：

```python
@dataclass(frozen=True)
class Theme:
    # ...既有欄位保留...

    # 卡片 / 表面層次
    surface_card: str          # 卡片底色（與 surface 微差，營造層次）
    surface_card_hover: str
    surface_sunken: str        # 凹陷區（例如 detail panel 背景）
    shadow_rgba: str           # e.g. "0,0,0,0.08"

    # 語意色：五個風險層級各一組（前景色 + 背景 tint + 邊框）
    layer_safe_fg: str
    layer_safe_bg: str
    layer_safe_border: str
    layer_process_fg: str
    layer_process_bg: str
    layer_process_border: str
    layer_review_fg: str
    layer_review_bg: str
    layer_review_border: str
    layer_registry_fg: str
    layer_registry_bg: str
    layer_registry_border: str
    layer_blocked_fg: str
    layer_blocked_bg: str
    layer_blocked_border: str

    # 形狀 token
    radius_sm: str = "6px"
    radius_md: str = "10px"
    radius_lg: str = "14px"
    radius_pill: str = "999px"
```

**建議色值**（Graphite Light）：

| layer | fg | bg | border |
|---|---|---|---|
| safe | `#047857` | `#ecfdf5` | `#a7f3d0` |
| process | `#0369a1` | `#f0f9ff` | `#bae6fd` |
| review | `#b45309` | `#fffbeb` | `#fde68a` |
| registry | `#be123c` | `#fff1f2` | `#fecdd3` |
| blocked | `#475569` | `#f8fafc` | `#cbd5e1` |

`surface_card = "#ffffff"`，`surface_card_hover = "#f9fafb"`，`surface_sunken = "#f3f4f6"`，`shadow_rgba = "15, 23, 42, 0.08"`。

**驗收**：`theme_by_name("graphite-light").layer_safe_bg == "#ecfdf5"`；現有 `dock_stylesheet`、`preferences_stylesheet` 不受影響。

### 1.2 新增 `safe_cleanup_stylesheet(theme)` helper

**目的**：把整份 dialog 的 QSS 集中。

**檔案異動**：`launcher/ui/theme.py` 末尾新增函式。

**關鍵程式碼**：

```python
def safe_cleanup_stylesheet(theme: Theme = DEFAULT_LIGHT) -> str:
    return f"""
    SafeCleanupDialog {{
        background: {theme.panel};
        color: {theme.text};
        font-family: {theme.font_family};
        font-size: {theme.font_size};
    }}
    QFrame#Card {{
        background: {theme.surface_card};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_md};
    }}
    QFrame#Card[hovered="true"] {{
        background: {theme.surface_card_hover};
        border-color: {theme.border_strong};
    }}
    QLabel#H1 {{ font-size: 20px; font-weight: 600; }}
    QLabel#H2 {{ font-size: 15px; font-weight: 600; }}
    QLabel#Muted {{ color: {theme.muted_text}; }}
    QLabel#Mono {{ font-family: "Cascadia Code", "Consolas", monospace; font-size: 12px; }}

    RiskBadge[layer="safe"]     {{ background:{theme.layer_safe_bg};     color:{theme.layer_safe_fg};     border:1px solid {theme.layer_safe_border};     border-radius:{theme.radius_pill}; padding:2px 10px; }}
    RiskBadge[layer="process"]  {{ background:{theme.layer_process_bg};  color:{theme.layer_process_fg};  border:1px solid {theme.layer_process_border};  border-radius:{theme.radius_pill}; padding:2px 10px; }}
    RiskBadge[layer="review"]   {{ background:{theme.layer_review_bg};   color:{theme.layer_review_fg};   border:1px solid {theme.layer_review_border};   border-radius:{theme.radius_pill}; padding:2px 10px; }}
    RiskBadge[layer="registry"] {{ background:{theme.layer_registry_bg}; color:{theme.layer_registry_fg}; border:1px solid {theme.layer_registry_border}; border-radius:{theme.radius_pill}; padding:2px 10px; }}
    RiskBadge[layer="blocked"]  {{ background:{theme.layer_blocked_bg};  color:{theme.layer_blocked_fg};  border:1px solid {theme.layer_blocked_border};  border-radius:{theme.radius_pill}; padding:2px 10px; }}

    QPushButton#Primary {{
        background: {theme.primary};
        color: white;
        border: none;
        border-radius: {theme.radius_md};
        padding: 10px 20px;
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background: {theme.primary_hover}; }}
    QPushButton#Ghost {{
        background: transparent;
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: {theme.radius_md};
        padding: 8px 14px;
    }}
    QPushButton#Ghost:hover {{ background: {theme.surface_alt}; }}

    QTabBar::tab {{
        padding: 8px 16px;
        margin-right: 4px;
        border: none;
        border-bottom: 2px solid transparent;
        color: {theme.muted_text};
        background: transparent;
    }}
    QTabBar::tab:selected {{
        color: {theme.primary};
        border-bottom: 2px solid {theme.primary};
        font-weight: 600;
    }}
    """
```

**驗收**：`SafeCleanupDialog` 改用 `safe_cleanup_stylesheet(theme)`；舊的 `preferences_stylesheet()` 仍保留給其他 dialog 用。

---

## 2. 整體版面重新組織

### 2.1 新框架：Header + Tabs + Sticky Footer

**目的**：現在的「target 控制列 + 兩欄 splitter + checkbox toggles + 詳細欄」資訊密度太高、視覺平鋪。重新切成：

```
┌─────────────────────────────────────────────────────────────┐
│ Header（目標卡片＋整體風險度＋一鍵安全清除 CTA）              │  ← 永遠在最上
├─────────────────────────────────────────────────────────────┤
│  [概覽] [清除建議] [隔離區] [活動紀錄]                       │  ← QTabWidget
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Tab 內容區（可捲動）                                        │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│ Sticky Footer（取消／重新分析／管理隔離區／關閉）             │
└─────────────────────────────────────────────────────────────┘
```

**檔案異動**：`launcher/ui/safe_cleanup_dialog.py` 大改 `__init__` 的版面組裝段（行 75–242 整段）。原本的 `QSplitter` + checkbox toggles + plain `QPlainTextEdit` 改為 tab widget 結構。

**關鍵程式碼骨架**：

```python
class SafeCleanupDialog(QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        # ...保留既有 worker / state 欄位...

        self._header = TargetHeaderCard()
        self._header.analyze_requested.connect(self._on_header_analyze)
        self._header.one_click_requested.connect(self._on_one_click_clean)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._overview_tab = OverviewTab()
        self._suggestion_tab = SuggestionTab()
        self._quarantine_tab = QuarantineTab()       # 內嵌 QuarantineBrowserDialog 內容
        self._activity_tab = ActivityLogTab()
        self._tabs.addTab(self._overview_tab, "概覽")
        self._tabs.addTab(self._suggestion_tab, "清除建議")
        self._tabs.addTab(self._quarantine_tab, "隔離區")
        self._tabs.addTab(self._activity_tab, "活動紀錄")

        self._footer = StickyActionBar()
        self._footer.cancel_clicked.connect(self.cancel_scan)
        self._footer.refresh_clicked.connect(self.refresh_plan)
        self._footer.close_clicked.connect(self.accept)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 0)
        root.setSpacing(14)
        root.addWidget(self._header)
        root.addWidget(self._tabs, 1)

        footer_wrap = QFrame()
        footer_wrap.setObjectName("FooterWrap")
        footer_layout = QVBoxLayout(footer_wrap)
        footer_layout.setContentsMargins(20, 12, 20, 16)
        footer_layout.addWidget(self._footer)
        root.addWidget(footer_wrap)

        self.setStyleSheet(safe_cleanup_stylesheet(theme_by_name(state.theme)))
        self.setMinimumSize(1200, 760)
        self.refresh_plan()
```

**驗收**：

- 開啟 dialog 後可看到 Header / Tabs / Footer 三段。
- 切換 tab 時，Header 與 Footer 不重繪、不閃動。
- Tab 內容區可內捲不影響 Footer。

### 2.2 卡片基底元件 `Card`

**目的**：所有卡片共用一致的陰影 + 圓角 + padding。

**新增檔案**：`launcher/ui/components/card.py`（同時建 `launcher/ui/components/__init__.py`）。

**關鍵程式碼**：

```python
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QVBoxLayout
from PyQt6.QtGui import QColor

class Card(QFrame):
    def __init__(self, parent=None, *, padding: int = 16, shadow: bool = True):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("hovered", False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(10)
        self._body = layout
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(18)
            effect.setOffset(0, 4)
            effect.setColor(QColor(15, 23, 42, 28))
            self.setGraphicsEffect(effect)

    def body(self) -> QVBoxLayout:
        return self._body

    def enterEvent(self, event):
        self.setProperty("hovered", True)
        self.style().unpolish(self); self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("hovered", False)
        self.style().unpolish(self); self.style().polish(self)
        super().leaveEvent(event)
```

**驗收**：Card 在 hover 時邊框會變色，並有柔和陰影；其他 dialog 也可直接 import 使用。

---

## 3. Header（目標卡片）

### 3.1 `TargetHeaderCard`

**目的**：取代原本「分析目標」那一排輸入框 + 6 顆按鈕。改成一張大卡片，包含：

- 大字目標名稱（含檔案圖示，從 `QFileIconProvider` 取）
- 副標：完整路徑 + 類型 + 大小（mono 字體）
- 右側：**整體風險度條**（segmented bar，5 段比例）
- 最右側：**一鍵安全清除** 主按鈕、**重新分析** ghost 按鈕、**選擇其他目標** ghost 按鈕（點開選單：應用 / 檔案 / 資料夾 / 直接輸入）

**新增檔案**：`launcher/ui/safe_cleanup/header_card.py`。

**關鍵程式碼骨架**：

```python
class TargetHeaderCard(Card):
    analyze_requested = pyqtSignal(object)         # 帶 LauncherContext
    one_click_requested = pyqtSignal()
    pick_app_requested = pyqtSignal()
    pick_file_requested = pyqtSignal()
    pick_folder_requested = pyqtSignal()

    def set_plan(self, plan: CleanupPlan): ...
    def set_scanning(self, active: bool): ...
```

`set_plan` 依 `plan.targets[0]` 渲染標題、路徑、大小；依 `plan.count_by_layer(...)` 算各層比例，更新 `RiskMeter`。

### 3.2 `RiskMeter`（風險度條）

**新增檔案**：`launcher/ui/safe_cleanup/risk_meter.py`。

**設計**：水平 segmented bar，高 8px、圓角 `radius_pill`，5 段以五個層級顏色比例渲染。下方一行「綠 12｜藍 1｜橘 4｜紅 2｜灰 3｜總計 22 項」。

**實作要點**：用 `QPainter.fillRect` 自繪 5 段，每段寬 = (count / total) × width。當 `total == 0` 顯示空灰底＋「尚未分析」。

**驗收**：當 plan 只有 SAFE 項目時，整條全綠；當有 BLOCKED 時，灰段一定顯示，提醒「有系統層需要管理員」。

---

## 4. 「概覽」Tab

### 4.1 統計卡片組

**目的**：取代原本 `_summary` 單行字串。

**新增檔案**：`launcher/ui/safe_cleanup/overview_tab.py`。

**版面**：上方一個 3 欄 ×2 列的 `QGridLayout`，6 張 `StatCard`：

1. 安全可清（綠）— 數量、估計可釋出空間
2. 執行中／佔用（藍）— 程序數，需手動關閉提示
3. 需要人工確認（橘）— 數量
4. 登錄檔 HKCU（紅）— 數量
5. 系統層待管理員（灰）— 數量；副文：「需另外啟動深度清理」
6. 找到的官方解除安裝（紫色強調）— 數量；副文：「建議先跑官方解除安裝」

點任一卡片→切到「清除建議」tab，並自動展開對應分組。

### 4.2 `StatCard`

**新增檔案**：`launcher/ui/safe_cleanup/stat_card.py`。

```python
class StatCard(Card):
    clicked = pyqtSignal(str)   # layer or kind id

    def __init__(self, *, title: str, layer: str, parent=None):
        super().__init__(parent, padding=18)
        self._layer = layer
        self._title = QLabel(title); self._title.setObjectName("Muted")
        self._value = QLabel("0"); self._value.setObjectName("H1")
        self._sub = QLabel(""); self._sub.setObjectName("Muted")
        self._badge = RiskBadge(layer=layer, text=_layer_label(layer))
        # 排版：左上 title + value，右上 badge，下方 sub
```

`mousePressEvent` 觸發 `clicked.emit(layer)`，並做 0.05s 縮放動畫（`QPropertyAnimation` on `geometry`，scale 1.0 → 0.98 → 1.0）。

### 4.3 官方解除安裝橫幅

**目的**：原本 `_uninstall_panel` 是一條灰色橫條，改成更明顯的「**建議優先動作**」卡片，黃色背景、配 ⚡ icon、按鈕「執行官方解除安裝」。如果沒有官方解除安裝候選，整個橫幅隱藏。

### 4.4 一鍵安全清除 CTA（在 Header 與 Overview 都出現一次）

**對話框流程**見 §6。

---

## 5. 「清除建議」Tab — 從 QTreeWidget 升級

### 5.1 整體結構

**目的**：原本的 5 欄 `QTreeWidget`（套用 / 清除建議 / 動作 / 判斷註解 / 位置）資訊密度高、不夠視覺化。改成：

```
┌─[左側 320px：層級篩選 sidebar]─┬─[中央：項目卡片列]──────┬─[右側 360px：詳細側欄]─┐
│  ☐ 全部 (22)                  │  ┌─卡片─────────────┐  │  選中項目的標題         │
│  ● 安全可清 (12)              │  │ ☑ icon  標題      │  │  路徑 / mono           │
│  ● 執行中 (1)                 │  │   副標 + badges   │  │  影響預估              │
│  ● 需確認 (4)                 │  │   牽連數          │  │  動作                  │
│  ● 登錄檔 HKCU (2)            │  └──────────────────┘  │  「定位來源」按鈕      │
│  ● 系統層 (3)                 │   ...                  │                        │
│                              │                        │                        │
│  ─ 動作開關 ─                 │                        │                        │
│  [⚙ 允許需確認層]              │                        │                        │
│  [⚙ 允許關閉程序]              │                        │                        │
│  [⚙ 允許登錄檔 HKCU]           │                        │                        │
└─────────────────────────────┴────────────────────────┴────────────────────────┘
```

**新增檔案**：

- `launcher/ui/safe_cleanup/suggestion_tab.py`
- `launcher/ui/safe_cleanup/item_card.py`
- `launcher/ui/safe_cleanup/detail_side_panel.py`
- `launcher/ui/safe_cleanup/risk_badge.py`
- `launcher/ui/safe_cleanup/toggle_card.py`

### 5.2 `ItemCard`（取代每一列 `QTreeWidgetItem`）

```python
class ItemCard(Card):
    toggled = pyqtSignal(str, bool)         # plan_item.id, checked
    selected = pyqtSignal(str)

    def __init__(self, item: CleanupPlanItem, parent=None):
        super().__init__(parent, padding=14, shadow=False)
        self._item = item
        self._checkbox = QCheckBox()
        self._icon = QLabel()                # 用 _item_icon(item)
        self._title = QLabel(item.label); self._title.setObjectName("H2")
        self._note = QLabel(item.note); self._note.setObjectName("Muted"); self._note.setWordWrap(True)
        self._location = QLabel(_item_location(item)); self._location.setObjectName("Mono")
        self._layer_badge = RiskBadge(layer=item.layer, text=_layer_label(item.layer))
        self._impact_badge = ImpactBadge(item)      # 顯示「牽連 N」
        # ...排版：左：checkbox + icon；中：title / note / location；右：badge column
```

可執行時整張卡片可勾選；不可執行時：

- checkbox 換成 lock 圖示
- 整張卡片明度降低 60%
- hover 顯示「為什麼不能勾」tooltip（內容沿用 `_non_apply_status` 的判斷）

### 5.3 `RiskBadge`

```python
class RiskBadge(QLabel):
    def __init__(self, *, layer: str, text: str, parent=None):
        super().__init__(text, parent)
        self.setProperty("layer", layer)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
```

樣式靠 QSS（見 §1.2）。

### 5.4 `ImpactBadge`（影響預估）

**目的**：實現之前的清單第 1 點「牽連數徽章」。

**計算邏輯**：在 `launcher/core/safe_cleanup.py` 新增 helper `compute_impact(plan, item) -> ItemImpact`，回傳：

```python
@dataclass(frozen=True)
class ItemImpact:
    shortcut_count: int        # 指向此 path 的捷徑
    registry_ref_count: int    # 登錄檔 value data 中提到此 path 的數量
    process_count: int         # 正在使用此 path 的程序
    derived_count: int         # 同名 / 衍生檔
```

UI 在每張卡片右下顯示：`🔗 3｜📋 2｜⚙ 1`（含 tooltip 解釋）。當所有計數皆 0 時不顯示 badge。

### 5.5 `ToggleCard`（動作開關）

**目的**：取代原本一字排開的 3 個 checkbox。

**設計**：每張卡片高 72px，左側圓形 icon（綠/橘/紅）、中間「標題 + 風險預估」、右側 `QSlider` 或自繪 toggle switch。

範例：

```
┌──────────────────────────────────────────────────────────┐
│ ⚠   允許執行需確認層                                       ●○│  ← 關
│     資料夾與疑似衍生檔需要人工確認。開啟後新增 4 項可勾。   │
└──────────────────────────────────────────────────────────┘
```

開啟瞬間，受影響的 `ItemCard` 用 200ms 淡入動畫從 disabled 變 enabled，視覺上有「解鎖」感。

### 5.6 `DetailSidePanel`

**目的**：取代原本底部一片 `QPlainTextEdit`。

**結構**：上半 = 結構化欄位（兩欄表格、圖示、可複製按鈕）；下半 = 兩個動作按鈕「定位來源」「複製路徑」。對 BLOCKED 層項目，下半多一個淡黃色提示卡，列重裝影響、為什麼不能勾、處理方式（內容沿用 `_update_detail` 行 776–779 的字串）。

---

## 6. 一鍵安全清除流程

### 6.1 流程圖

```
[Header 按下「一鍵安全清除」]
        │
        ▼
[OneClickSummaryDialog]
  顯示：找到 X 個目標 / 將清 Y 項（依預設規則勾選）/ 不會碰什麼 / 保留 30 天可還原
  按鈕：[取消] [確認執行]
        │
        ▼ 確認
[執行 apply_cleanup_plan(...)]
  使用 §6.3 的「預設一鍵規則」自動產生 selected_ids
  progress 沿用既有 _on_apply_progress
        │
        ▼ 完成
[OneClickResultDialog]
  顯示：✓ 已隔離 N 個項目 / 隔離區位置 / Restore-Registry.ps1 路徑
  按鈕：[全部還原（30 天內可用）] [打開隔離區] [完成]
```

### 6.2 `OneClickSummaryDialog`

**新增檔案**：`launcher/ui/safe_cleanup/one_click_dialogs.py`。

**設計**：

- 標題：`即將安全清除：{target_name}`
- 三張小卡片：
  - 綠：將清除 N 項（safe + review 預設項）
  - 橘：暫不處理 M 項（執行中 / 系統層）→「為什麼？」連結
  - 藍：將保留 30 天，可隨時還原
- 警告紅字：**不會處理 HKLM／Windows Installer 殘留**；需另外啟動「管理員深度清理」（連結放在底部 ghost 按鈕，未實作前先 disabled 並標「即將推出」）。

### 6.3 預設一鍵規則（寫在 dialog，方便測試）

```python
def default_one_click_ids(plan: CleanupPlan) -> set[str]:
    keep_layers = {SAFE_LAYER, REVIEW_LAYER}   # process/registry/blocked 一律 opt-in，不一鍵
    return {item.id for item in plan.items if item.layer in keep_layers and item.executable and item.checked_default}
```

注意：**registry 不進一鍵**。理由：HKCU 雖然較安全，但對非工程師而言「動到登錄檔」字眼仍嚇人，預設手動勾比較穩。如未來決定加入，可在偏好設定加 toggle。

### 6.4 `OneClickResultDialog`

- 大綠勾 ✓（可用 QSvgWidget，附一個 800ms 的 stroke 動畫，見 §7.3）
- 結果條列（沿用 `_on_apply_finished` 的 `lines`）
- 主按鈕：「打開隔離區」（切到 §4 的隔離區 tab）
- 次要：「全部還原」— 呼叫即將新增的 `apply_restore_all(manifest_id)`（如 core 尚未實作，先 disabled 並標「即將推出」）

### 6.5 觸發點

Header 與 Overview 的「一鍵安全清除」CTA 都連到 `SafeCleanupDialog._on_one_click_clean`。掃描中或套用中時，按鈕呈現 loading 狀態（spinner + disabled）。

---

## 7. 動畫與微互動

### 7.1 階段步進指示器

**目的**：取代原本 8px 細條 `QProgressBar`。

**新增檔案**：`launcher/ui/safe_cleanup/stage_stepper.py`。

**設計**：水平 9 個圓點（對應 `_SCAN_STAGES`），目前 stage 的點放大 1.4×、發光（drop shadow），已完成的點實心、尚未到的虛線描邊。中央同步顯示 stage 名稱。

**動畫**：點亮新 stage 時，舊點縮回 1.0× 過渡 200ms，新點放大 200ms，文字 200ms 淡入。

### 7.2 卡片 hover

所有 `Card` 子類 hover 時：

- 邊框色 → `border_strong`
- 陰影 blur 18 → 24，offset (0,4) → (0,6)
- 200ms `QPropertyAnimation` 平滑過渡（對 `QGraphicsDropShadowEffect.blurRadius`）

### 7.3 成功動畫（清除完成）

在 `OneClickResultDialog` 與一般 `_on_apply_finished` 都用。建議方式：用 QSvgWidget 載入內嵌的 checkmark SVG（path），對 `stroke-dashoffset` 做 600ms 動畫。SVG 與動畫 helper 放在 `launcher/ui/components/check_animation.py`。

### 7.4 Skeleton loading

掃描中時，「概覽」tab 的 6 張 `StatCard` 內容用 skeleton（灰色圓角矩形 + 1.2s 來回 shimmer）顯示，比起當前的 `_show_scan_placeholder` 文字「分析中...」更有質感。`SkeletonBlock` 元件放在 `launcher/ui/components/skeleton.py`，用 `QPropertyAnimation` 對自繪 gradient offset 來回過渡。

### 7.5 Tab 切換

`QTabWidget` 預設切換是 instant。加 100ms opacity 過渡（用 `QGraphicsOpacityEffect` + `QPropertyAnimation`）。

---

## 8. 空狀態與引導

**目的**：原本啟動時空 dialog 看不出怎麼開始。

**新增**：當 `context` 沒有任何 target 時，「概覽」tab 顯示 `EmptyState` 元件：

- 上：一張內嵌 SVG 插畫（簡單線條，主題色描邊；可放在 `launcher/resources/illustrations/empty_target.svg`）
- 中：標題「選一個目標開始」
- 下：三顆大按鈕，並排，每顆有 icon：
  - 選擇應用 / 選擇檔案 / 選擇資料夾
- 最底：小字「也可以把檔案直接拖到這個視窗」+ 一個淡灰虛線框 drop zone（接 `dragEnterEvent` / `dropEvent`）

**驗收**：將檔案拖到 dialog 任何位置都會自動切到「清除建議」並開始分析；視窗有藍色 drop highlight（`drop_bg`）。

---

## 9. 主題與密度

### 9.1 暗色主題

新增 `GRAPHITE_DARK` Theme：

- `panel = "#0f172a"`
- `surface = "#1e293b"`
- `surface_card = "#1e293b"`
- `surface_card_hover = "#273449"`
- `surface_sunken = "#0b1220"`
- `text = "#e2e8f0"`
- `muted_text = "#94a3b8"`
- `border = "#334155"`
- 風險五色 bg 改用 8% alpha 的同色（例：`layer_safe_bg = "rgba(16,185,129,0.12)"`），fg 維持鮮豔。

`preferences_dialog` 加 dropdown「外觀」：自動跟隨系統 / Graphite Light / Graphite Dark / Engineering Blue 2.0。

### 9.2 密度切換

在「動作開關」區下方加一個小型 segmented control「舒適 / 緊湊」，存到 `state.json`。

- 舒適：卡片 padding 16、卡片間距 12、字級 13/15/20
- 緊湊：padding 10、間距 8、字級 12/14/18

---

## 10. 檔案對應與優先順序

### 10.1 新增檔案清單

```
launcher/ui/components/__init__.py
launcher/ui/components/card.py
launcher/ui/components/check_animation.py
launcher/ui/components/skeleton.py
launcher/ui/safe_cleanup/__init__.py
launcher/ui/safe_cleanup/header_card.py
launcher/ui/safe_cleanup/risk_meter.py
launcher/ui/safe_cleanup/risk_badge.py
launcher/ui/safe_cleanup/impact_badge.py
launcher/ui/safe_cleanup/stat_card.py
launcher/ui/safe_cleanup/overview_tab.py
launcher/ui/safe_cleanup/suggestion_tab.py
launcher/ui/safe_cleanup/item_card.py
launcher/ui/safe_cleanup/toggle_card.py
launcher/ui/safe_cleanup/detail_side_panel.py
launcher/ui/safe_cleanup/stage_stepper.py
launcher/ui/safe_cleanup/quarantine_tab.py
launcher/ui/safe_cleanup/activity_log_tab.py
launcher/ui/safe_cleanup/one_click_dialogs.py
launcher/resources/illustrations/empty_target.svg
tests/test_safe_cleanup_overview_tab.py
tests/test_safe_cleanup_one_click.py
tests/test_safe_cleanup_components.py
```

### 10.2 修改檔案清單

- `launcher/ui/theme.py` — §1
- `launcher/ui/safe_cleanup_dialog.py` — §2.1 整體重組；保留對外 API
- `launcher/core/safe_cleanup.py` — §5.4 新增 `compute_impact` 與 `ItemImpact`；§6.4 預留 `apply_restore_all`（未實作前丟 `NotImplementedError`）
- `launcher/ui/preferences_dialog.py` — §9.1 外觀 dropdown
- `tests/test_safe_cleanup_dialog.py` — 對應新 API 調整

### 10.3 建議優先順序（每個 sprint 一塊）

1. **Sprint A — 視覺骨架**：§1（theme tokens）+ §2（框架）+ §2.2（Card）+ §5.3（RiskBadge）
2. **Sprint B — 概覽 tab**：§3（Header＋RiskMeter）+ §4（StatCard 與 Overview）
3. **Sprint C — 一鍵安全清除**：§6 全部
4. **Sprint D — 清除建議改造**：§5（ItemCard / ToggleCard / DetailSidePanel）+ §5.4 ImpactBadge
5. **Sprint E — 動畫與打磨**：§7（StageStepper、hover、success、skeleton、tab 過渡）
6. **Sprint F — 引導與主題**：§8（空狀態 + drop zone）+ §9（暗色主題 + 密度）

A、B、C 完成後使用者就會感覺到「明顯漂亮 + 一鍵可用」；D、E、F 是把整體質感推到位。

---

## 11. 不在這份指令書範圍

- 「管理員深度清理」流程（會處理 HKLM / Windows Installer 殘留）。Header 的入口先 disabled 並標「即將推出」，等下一份指令書專門做。
- 隔離區的保留期/容量上限自動清理。`QuarantineTab` 只先做唯讀展示與「打開資料夾／還原單項」。
- 多選與批次操作的進階互動（如 shift-click 選取範圍）。
- i18n / 英文版。本輪維持繁體中文字串。

---

**完工檢查清單**

- [ ] `pytest` 全綠
- [ ] dialog 在 1280×800 與 1920×1080 都沒水平捲軸、無重疊
- [ ] 「一鍵安全清除」全程仍呼叫 `apply_cleanup_plan(...)`，產出 manifest（grep `quarantine_manifest_json` 確認）
- [ ] HKLM / Windows Installer 殘留在新 UI 仍無法被一般使用者勾選或執行
- [ ] 暗色主題開啟後對比度通過 WCAG AA（前景/背景對比 ≥ 4.5）
- [ ] 所有新元件可以在 `python -m launcher.ui.safe_cleanup_dialog` 之外被獨立 import（沒有循環依賴）
