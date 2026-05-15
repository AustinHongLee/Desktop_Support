# Codex 修改 Review — v0.1

> 對照基準:`docs/設計建議_面板與延伸定位.md`
> Review 範圍:Codex 本輪改動的 12 個檔案

---

## 1. 總評

整體完成度高,Sprint 1 + Sprint 2 + Sprint 3 大部分功能都到位,而且做了我沒明確要求但有附加價值的功能(Plugin Manager、Registry 載入問題回報、Run timeout/cancel、JobMonitor 三個 tab)。架構切割也對 — `EdgePositioner` / `palette_search` 都拆成純函式可單獨測試。

但有 **3 個明顯 bug** 必須修、**5 個落差**(設計裡寫了 Codex 沒做)、和 **若干小毛病**。詳如下。

---

## 2. 做得好的部分(可直接保留)

| 領域 | 表現 |
| - | - |
| `theme.py` | 變數命名乾淨、`role="primary"` / `sourceKind` / `state="ok"` 等 dynamic property 用法正確,QSS unpolish/polish 也對 |
| `edge_positioner.py` | 純資料/純函式,沒依賴 Qt widget,容易測試;`screen_area_from_qrect` 把 Qt → dataclass 的 adapter 抽出來是對的 |
| `palette_search.py` | subsequence + token + title bonus + category bonus + recent weight 的設計比預期完整 |
| `CommandPalette` | `eventFilter` 攔 ↑/↓ 和 Esc、`Ctrl+1..9` 直接執行、分組顯示 + recent badge — 與設計一致 |
| `JobMonitor` | status label + state property + 三個 tab(全部/錯誤/產出)+ 取消 + 複製紀錄 |
| `ActionRunner` | `RunControl` thread-safe(用 lock)、`_drain_worker` 用 queue + 0.05s tick 同時處理 cancel/timeout/stdout — 設計很穩 |
| `state_store._save` | `os.replace` atomic 寫入,失敗時清掉 tmp 檔 ✓ |
| `state_store._load` | 改成具體 `JSONDecodeError, OSError`,且 `isinstance(data, dict)` 驗證 ✓ |
| `ActionRegistry` | 改回傳 `RegistryLoadReport`,單一 plugin 壞掉不會炸掉整個 load — 比設計建議還多 |
| `JobResult.ok` | 同時看 return_code 和 events 裡的 error/cancelled/timeout — 嚴謹 |

---

## 3. Bug(建議優先修)

### 🔴 Bug 1 — Palette 在 query 為空時排序不符合使用者期待

**位置**:`launcher/ui/palette_search.py` 第 34 行

```python
return sorted(matches, key=lambda match: (-match.score, match.action.category, match.action.title))
```

**問題**:當 query 為空時,score 只剩 `_recent_score`(每名相差 12 分)。但 fallback sort 是 `(category, title)`,所以同一個 category 裡 recent 第 1 名與第 2 名雖然分數差 12,排序上是用 -score 先排,**沒問題**。

仔細看一次:`-score` 先,所以 recent 第 1(最高分)會在 recent 第 2 前面。**這條判斷錯了,沒 bug**。

但仍有一個真實問題:**Recent 不在使用者期望的群組順序內**。
`_group_matches` 是 OrderedDict by 出現順序;`matches` 本身是按 (-score, category, title) 排;當 recent_action_ids = [A(分類:工具), B(分類:檔案), C(分類:工具)],排出來會是 `A(工具,score 36)`, `B(檔案,score 24)`, `C(工具,score 12)` → group 顯示 `工具: [A, C]`、`檔案: [B]`,而 `工具` 群組會出現在最前面 — **這個是對的,但「最近」資訊在群組裡會散開**。

**建議**:加一個獨立的「最近指令」群組固定在最頂,類似 Raycast 的 "Suggested"。實作:

```python
# 在 _refresh 顯示時:
recent_matches = [m for m in matches if m.action.id in self._recent_action_ids][:5]
other_matches  = [m for m in matches if m not in recent_matches]
# 顯示 "最近" 群組 → 各 category 群組
```

### 🔴 Bug 2 — `_apply_dock_preferences` 在「auto_hide 沒變但 edge / screen 變了」時沒重新定位

**位置**:`launcher/ui/dock_window.py` 第 563-570 行

```python
def _apply_dock_preferences(self) -> None:
    self._hide_timer.stop()
    self._hide_timer.setInterval(self._state_store.auto_hide_delay_ms)
    if self._state_store.auto_hide_enabled:
        self._set_collapsed(True)        # ← 內部會 _snap_to_edge,OK
    else:
        self._collapsed = False
        self._snap_to_edge()              # ← 也 OK
```

實際追進去 `_set_collapsed(True)` → `_snap_to_edge()` 會重新算 edge / screen,**所以這條其實沒事**。

但這裡有另一個真的 bug:**使用者開偏好設定 → 把 auto_hide 從 True 改成 False → 按套用**,流程進入 `else` 分支,設 `_collapsed = False; _snap_to_edge()`。看似 OK,但 `_collapsed = False` 是直接賦值不過 `_set_collapsed`,**不會 emit raise_()**;dock 已經是 collapsed 狀態(視窗只有 130×16),展開後高度變了但畫面可能還停在原地 — 視 Qt 行為而定,建議統一走 `_set_collapsed(False)`,但 `_set_collapsed(False)` 內部有

```python
if collapsed and not self._state_store.auto_hide_enabled:
    return
```

把 `False` 傳進去不會 return,所以可以直接用。**修法**:把 else 分支改成:

```python
else:
    self._set_collapsed(False)
```

### 🔴 Bug 3 — Dock 進入拖放(dragEnter)時若處於 collapsed,沒有自動展開

**位置**:`launcher/ui/dock_window.py` 第 235-238 行

`dragEnterEvent` 只 set `dropTarget` property,沒處理 collapsed → expanded。tail bar 只有 130×16 px,**幾乎沒辦法把檔案拖到那麼小的目標上**,設計建議裡的「拖放回饋」會在 collapsed 時失效。

**修法**:

```python
def dragEnterEvent(self, event: QDragEnterEvent) -> None:
    if event.mimeData().hasUrls():
        self._hide_timer.stop()
        if self._state_store.auto_hide_enabled and self._collapsed:
            self._set_collapsed(False)
        self._set_drop_target_active(True)
        event.acceptProposedAction()
```

---

## 4. 落差(設計裡寫了,本輪沒做)

| # | 項目 | 影響 |
| - | - | - |
| L1 | **theme 只實作 `DEFAULT_LIGHT`,沒有 dark / high-contrast** | 偏好設定也沒「主題」選項。Sprint 1 應該完成 |
| L2 | **「最近指令 / 最近檔案 / 最近資料夾」沒合併成一顆下拉** | dock 反而多了「外掛」按鈕,水平模式更擁擠 |
| L3 | **palette 沒有中文拼音首字母**(pypinyin) | 純英文輸入無法命中中文 action,例如「ya」想找「壓縮」 |
| L4 | **沒有全域熱鍵**(`Ctrl+Alt+Space` 等) | 還是只有 dock focus 時的 Ctrl+K |
| L5 | **沒有任何單元測試**(`test_edge_positioner` / `test_palette_search` / `test_state_store_atomic` / `test_registry_loader`) | 未來改動容易回歸;這幾個檔案剛拆出來,是測試 ROI 最高的時機 |
| L6 | **bootstrap 拿到 `registry.load()` 回傳的 report 沒做事** | 啟動時 plugin 壞掉,使用者只能透過選單進 PluginManager 才看到問題;應該寫 log 或啟動時跳一次提示 |

---

## 5. 小毛病(可慢慢修)

1. **`state.json` 沒有 `schema_version` 欄位** — 未來改 schema 沒有遷移空間。建議 `_save` 時固定寫 `"schema_version": 1`。
2. **`_failure_event` 用最後 8 行 message 當 `recent_output`** — 若 plugin 輸出量大,訊息會被截斷;考慮限制 char 而非 line 數,並標明「(截斷)」。
3. **`Path.cwd()` 仍在 `pick_files` / `pick_folder` 開啟對話框時當預設路徑** — 應該用目前 context.folder 當預設(`QFileDialog.getOpenFileNames(self, "...", str(self._context.folder or Path.cwd()))`)。
4. **`PluginManagerDialog` 沒有「啟用/停用」單一 plugin** — 設計建議裡有提到 `enabled: true|false`,可以加在 `actions.json` 並反映在 dialog 的核取方塊;同時讓 `ActionRegistry.matching_actions` 過濾。
5. **`PluginManagerDialog._populate_issues` 直接 `setPlainText`** — 多次 reload 後不會 highlight 新問題;可以加時間戳或顏色。
6. **`CommandPalette._move_selection` 的 modulo 邏輯在「只有 header 沒 action」的情況會死循環** — 不會死循環(因為 step 上限),但會把 currentRow 留在 header 上。可以提早 return:`if not self._shortcut_action_ids: return`。
7. **`JobMonitor._request_cancel` 後若 worker 又送回 message event,status 不會被改寫成完成** — 因為 `_set_status` 只在特定事件觸發,使用者按了取消但 worker 其實順利結束,狀態還會停在「取消中」直到 `finish()` 被呼叫。`finish` 內已根據 events 判斷,所以最終狀態正確。可接受。
8. **`_apply_edge_layout` 在垂直模式把按鈕固定 `104×46`** — 多了「外掛」按鈕後高度可能超過 toolbar 區;雖然 `area.height = screen height` 通常夠,但小螢幕(13" / 1366×768)可能擠出 dock 外。建議按鈕高度視 dock 高度動態算。
9. **`reload_plugins` 用 `QMessageBox.information / warning`** — Modal 對話框會打斷使用者;考慮改 tray 的 toast 或在 dock 加個一行 status banner。
10. **`palette_search._normalize` 把 `_` `-` 全換成空白後 split** — 對英文 OK,對中文沒影響。但 query 同時有中英文(`pdf 壓縮`)會被切成兩個 token 各自找 subsequence,**可能很慢** 在大 action 表時;目前 action 數少不會有事,但設計上可加 short-circuit。
11. **沒有 logger** — `try/except` 多處仍 `pass` 或忽略,使用者沒辦法 debug。建議建立 `launcher/core/logging_config.py`。

---

## 6. 對「延伸定位」的進度

按設計裡 L1–L9 的視窗定位邏輯擴充,目前狀態:

| 編號 | 項目 | 狀態 |
| - | - | - |
| L1 | 記憶相對偏移 | ✗ 未做(只記 edge) |
| L2 | 多螢幕 hot-plug | ✗ 未監聽 `screenAdded/screenRemoved` |
| L3 | DPI 變更響應 | ✗ |
| L4 | 避開 auto-hide taskbar(SHAppBarMessage) | ✗ |
| L5 | 避開最大化前景視窗 | ✗ |
| L6 | 4 個螢幕角 mini-mode | ✗ |
| L7 | context 變更時暫時跨螢幕展開 | △ 已有 `_poll_context_inbox` 自動展開,但無「跨螢幕跟隨」 |
| L8 | 滑鼠停在螢幕邊緣自動展開 | ✗ |
| L9 | 每螢幕各一個 dock | ✗ |

→ 這些原本就排在 Sprint 4。**本輪沒做合理**,可以放下一輪。

---

## 7. 對「新外掛」的進度

`launcher/plugins/` 沒有新增 plugin。設計建議裡的「立刻就能加」5 個 plugin(quick_screenshot / clipboard_history / archive_tools / hash_tools / text_transform)都未動工。這也合理,因為 Sprint 5 排在後面,但可以**從 hash_tools 或 archive_tools 開始**(無外部依賴,可驗證 plugin 載入流程在 reload / 錯誤回報路徑是否真的順)。

---

## 8. 建議的下一個 PR 範圍

如果要分一個小 PR 收尾,建議優先順序:

1. **修 Bug 3(拖放自動展開)** — 影響使用者拖檔最大,1 行改動。
2. **修 Bug 2(`_apply_dock_preferences` 統一走 `_set_collapsed(False)`)** — 5 行,把 else 改乾淨。
3. **加 `test_edge_positioner.py` + `test_palette_search.py` + `test_state_store_atomic.py`** — 約 100 行測試,把剛拆出來的純函式 / dataclass 鎖住,防回歸。
4. **bootstrap 接收 `RegistryLoadReport`,有 issues 時 print/log 出來** — 5 行。
5. **加 `schema_version` 到 state.json + `theme` 設定欄位**(為下一輪 dark theme 做準備) — 10 行。

合計 ~150 行改動,可以一次完成。如果你想要,我可以直接接著動手做這 5 點,結束本輪 review 收尾。

---

## 9. 結論

Codex 把 Sprint 1 主軸(theme、dock 拖動、拖放回饋、context 來源色點、preferences、plugin manager)+ Sprint 2(palette fuzzy + 分組 + ctrl 1..9、JobMonitor tabs + cancel + timeout)+ Sprint 3 一半(edge_positioner 抽出、state_store atomic、registry report)**做完了**。

剩下的主要是:
- 3 個 bug 要修(都不大)
- 5 個設計裡寫了但沒做的(主題、合併 recent、拼音、全域熱鍵、單元測試)
- Sprint 4(延伸定位邏輯擴充)與 Sprint 5(新 plugin)還沒開始

整體可以 merge,但建議至少先修 Bug 3(拖放收合)再進。
