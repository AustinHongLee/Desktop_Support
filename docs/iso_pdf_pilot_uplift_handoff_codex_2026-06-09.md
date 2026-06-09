# ISO PDF Pilot 升級 — 交接書（給 Codex 接手）

> Date: 2026-06-09 · Branch `codex/tauri-react-spike` · base commit `97bb365`
> 設計母文件：`docs/iso_pdf_pilot_uplift_plan_2026-06-09.md`（先讀它的 §3-§7；本文件只補「現在做到哪、剩下怎麼做」）
> 接手者執行環境：你（Codex）在 Windows 本機，可正常 `git commit`、`.\scripts\test.ps1`、開 Tauri UI 截圖。前一手在 Linux sandbox，只能 `tsc --noEmit` + 後端 stdlib 測試，無法 commit / 開 UI，故以下「驗證」欄請你補上 build + UI 截圖。

---

## 0. 交接一句話

Pilot（`launcher/plugins/iso_tools/pilot.py` 的 P01-P12）後端早就把 `pilot_results`/`pilot_summary` 掛到每份 plan、寫進 run log/debug bundle，但 UI 過去只在 RunLogDrawer 用。本升級＝**把既有 Pilot 接進一鍵/工作台/調校**，不另造系統。Batch 1（型別/helper/共用元件 + 後端 schema v2）與 Batch 2（工作台掛 PilotStrip + 問題導航 + 修表格空白）**已完成且 `tsc` 綠**，未 commit。請接 Batch 3-5。

---

## 1. 不可違反的硬規則（每批都要守）

1. **P01-P12 的 `id` 與 `stage` 是凍結契約**（已落在 run.json、debug bundle `pilot.json`、前端 `pilotLabel`、`tests/test_iso_pilot.py`）。新增檢查一律 **append `P13`、`P14`…**，**禁止重新編號**。母文件 §4.1 有說明 Qwen 版 17 項與實作版編號錯位，不要照 Qwen 重編。
2. **不得新增 `PILOT_STATUSES` enum 值**（`pending/running/ready/warn/blocked/skipped` 固定）。stale / needs_review 用 **正交附加欄位** `freshness`（`"fresh"|"stale"`）、`needs_review`（bool）表達（Batch 1 已加好，schema v2）。
3. **不得破壞一鍵（Autopilot）流程與主按鈕語意**。Batch 4 碰一鍵時只加「投影/導引」，不改 `oneClickStage` 狀態機與 `runOneClick` 行為。
4. **不得移除 PyQt6 legacy**（`launcher/ui/iso_pdf_naming_dialog.py` 等），它仍是對照/測試線。`validator.py`（PF/E/W checklist）保留給 legacy，Tauri 端統一走 Pilot。
5. **維持 backend workflow contract**：`run_iso_workflow` 既有 action 的輸入/輸出 schema 不破壞；新增能力用新 action。
6. **分批 commit**，每批跑 `.\scripts\test.ps1 -Suite frontend`；碰 UI 的批次要開 Tauri UI 用 `C:\Users\a0976\Downloads\t` 實測 + **1181×790 與最大化各截圖**（實驗資料應得 4 ready / 0 warn / 0 blocked）。

---

## 2. 目前工作樹狀態（Batch 1 + 2，未 commit，`tsc --noEmit` = 0）

`git diff --stat`（相對 HEAD `97bb365`，忽略既有的 `App.tsx` 改動）：

```
 launcher/plugins/iso_tools/pilot.py                +14
 frontend/tauri-spike/src/isoWorkflow.ts            +17
 frontend/tauri-spike/src/iso/helpers.ts            +79
 frontend/tauri-spike/src/iso/IsoBoard.tsx          +31
 frontend/tauri-spike/src/iso/WorkbenchView.tsx     ~18
 frontend/tauri-spike/src/iso/components/NamingTable.tsx  +5
 frontend/tauri-spike/src/styles.css                +48
 (new) frontend/tauri-spike/src/iso/components/PilotStrip.tsx
 (new) frontend/tauri-spike/src/iso/components/PilotListPanel.tsx
```

建議先分兩個 commit 再續做：

```
git add launcher/plugins/iso_tools/pilot.py frontend/tauri-spike/src/isoWorkflow.ts frontend/tauri-spike/src/iso/helpers.ts frontend/tauri-spike/src/iso/components/PilotStrip.tsx frontend/tauri-spike/src/iso/components/PilotListPanel.tsx
git commit -m "feat(iso): add pilot UI types, helpers and shared components (batch 1)"
git add frontend/tauri-spike/src/iso/IsoBoard.tsx frontend/tauri-spike/src/iso/WorkbenchView.tsx frontend/tauri-spike/src/iso/components/NamingTable.tsx frontend/tauri-spike/src/styles.css
git commit -m "feat(iso): surface pilot summary and issue navigation in workbench (batch 2)"
```

> 雜項：工作樹有兩個前一手留下的探針檔，請刪除：`del .__bash_probe.txt .__gitprobe.txt`（`.qwen/` 是使用者既有，勿動）。

### 2.1 可直接重用的 API（Batch 3-5 請用這些，不要重造）

**後端 `pilot.py`（schema v2）**
- `PILOT_SCHEMA_VERSION = 2`，`PILOT_FRESHNESS = {"fresh","stale"}`。
- `_item(...)` 已接受並輸出附加欄位：`freshness="fresh"`、`needs_review=False`、`next_action=None`（後兩者目前 12 項都用預設）。
- 每項輸出含舊欄位 + `freshness`/`needs_review`/`next_action`。

**前端型別 `isoWorkflow.ts`**
- `IsoPilotItem` 新增 optional：`freshness?`、`needs_review?`、`next_action?: IsoPilotNextAction | null`。
- 新型別：`IsoPilotStatus`、`IsoPilotFreshness`、`IsoPilotView`、`IsoPilotNextAction{ label; view; anchor?; row_ref? }`。

**前端 helper `iso/helpers.ts`**
- `pilotTone(item): "ready"|"warn"|"danger"|"run"|"idle"`（含 stale/needs_review→warn）。
- `pilotFreshnessLabel(item)`（stale→「已過期」、needs_review→「未確認」）。
- `pilotLocation(item): IsoPilotNextAction`（先用 `item.next_action`，否則查 `PILOT_LOCATION_BY_STAGE`，已含 P13-P17 的 stage）。
- `pilotNextStep(items)`：回傳最急的可動項 `{ item, text, action }`。

**共用元件**
- `components/PilotStrip.tsx`：`<PilotStrip items={IsoPilotItem[]} onJump? title? />`（工作台已用）。
- `components/PilotListPanel.tsx`：`<PilotListPanel items onJump? onAutoFix? showEngineerDetail? />`（調校待掛，Batch 3 用）。

**`IsoBoard.tsx`**
- 已有 `handlePilotJump(item)`：engineer/autopilot→切 view；workbench→`anchor==="dryrun"` 開 dry-run，否則跳到 `row_ref`（`page:N`）或第一個 blocked/warn 列並開「只看問題」。
- 已把 `pilotItems={plan?.pilot_results ?? []}`、`onPilotJump={handlePilotJump}` 傳給 `WorkbenchView`。Batch 3/4 比照傳給 `EngineerView`/`AutopilotView`。

---

## 3. 待辦 Batch 3 — 調校 Pilot List + P13-P15 + ROI distribution

### 3A 前端（EngineerView 掛 PilotListPanel + stale 提醒）
- `IsoBoard.tsx`：給 `<EngineerView>` 傳 `pilotItems={plan?.pilot_results ?? []}`、`onPilotJump={handlePilotJump}`（可選 `onAutoFix`，先傳會觸發 `generatePlan` 的 handler 即可）。
- `EngineerView.tsx`：右欄 `aside.iso-engineer-panel`（目前有 `RoiSamplePanel` + legacy 卡）加 `<PilotListPanel items={pilotItems} onJump={onPilotJump} showEngineerDetail />`。新增對應 props 與型別。
- **stale 黃條**：當 `pilotItems.some(i => i.freshness === "stale")` 時，在 `main.iso-engineer-panel.wide` 頂端顯示「草稿已過期，請重生」＋按鈕 `generatePlan`。樣式可重用 `.batch-progress.warn` 類或新增 `.engineer-stale-banner`。

### 3B 後端（pilot.py 追加 P13/P14/P15，append-only）
在 `_build_items()` 的 `return [...]` 清單**末端**（P12 之後）追加三項，並把 `"P13","P14","P15"` 加進 `PILOT_ITEM_IDS`。下面是參考實作（依現有 helper `_int_value/_float_value/_path_exists/_pages` 調整）：

```python
# P13 — roi_confidence（整批判讀品質；blocks_apply=False）
conf = [_float_value(r.get("confidence"), 0.0) for r in rows if str(r.get("vision_message") or "").strip()]
avg = sum(conf) / len(conf) if conf else 0.0
low_ratio = (len(low_confidence_rows) / len(rows)) if rows else 0.0
roi_status = "ready" if (avg >= 0.85 and low_ratio < 0.10) else "blocked" if low_ratio > 0.50 else "warn" if rows and detect_serials else "skipped" if not detect_serials else "pending"
_item("P13", "roi_confidence", roi_status,
      "判讀品質良好。" if roi_status == "ready" else f"{len(low_confidence_rows)} 頁需確認（平均信心 {avg:.0%}）。",
      engineer_detail=f"avg={avg:.3f}; low_ratio={low_ratio:.2f}; low={len(low_confidence_rows)}",
      metrics={"avg_confidence": avg, "low_ratio": low_ratio},
      auto_fix="重新自動校準 ROI 或降低門檻。", manual_hint="到調校調整 ROI / 門檻。",
      blocks_apply=False,
      next_action={"label": "到調校檢查判讀品質", "view": "engineer", "anchor": "roi"}),

# P14 — profile_consistency（draft vs published / 檔案是否還在；可 block）
profile = source.get("profile") if isinstance(source.get("profile"), dict) else {}
missing = [k for k in ("iso_list", "page_folder", "combine_pdf")
           if str(source.get(k) or "").strip() and not _path_exists(source.get(k))]
draft_mismatch = bool(profile.get("draft_exists")) and not bool(profile.get("published_exists"))
p14_status = "blocked" if missing else "warn" if draft_mismatch else "ready"
_item("P14", "profile_consistency", p14_status,
      f"設定指向的檔案不存在：{', '.join(missing)}" if missing else "草稿尚未發布到一鍵。" if draft_mismatch else "Profile 一致。",
      engineer_detail=f"missing={missing}; draft_mismatch={draft_mismatch}",
      metrics={"missing": len(missing), "draft_mismatch": draft_mismatch},
      manual_hint="到調校重新選來源或發布草稿。",
      blocks_apply=bool(missing),
      next_action={"label": "到調校檢查 Profile", "view": "engineer", "anchor": "profile"}),

# P15 — draft_freshness（ROI/mapping/sheet/pattern 改過未重生；replay 與現況不同 → stale；不 block）
plan_src = source  # plan 的 source
req_keys = ("sheet_name", "serial_col", "line_col", "pattern")
changed = [k for k in req_keys if request.get(k) not in (None, "") and str(request.get(k)) != str(plan_src.get(k) or "")]
is_replay = str((job or {}).get("action") or plan_src.get("action") or "").endswith("replay_run_log")
stale = bool(changed) or is_replay
_item("P15", "draft_freshness", "warn" if stale else "ready",
      "設定已變更，草稿可能過期，建議重新產生。" if stale else "草稿與目前設定一致。",
      engineer_detail=f"changed={changed}; replay={is_replay}",
      metrics={"changed": changed},
      freshness="stale" if stale else "fresh",
      manual_hint="重新產生命名草稿。",
      blocks_apply=False,
      next_action={"label": "重新產生草稿", "view": "workbench", "anchor": "dryrun"}),
```

> 注意：P15 需要「plan.source 的設定」vs「目前 request」。`build_pilot_report` 已收 `request` 與 `plan`，`source` 來自 `_source_payload(request, plan)`——但它會用 request 補空值，故 P15 比對請改用 **plan 原始 source**（`plan.get("source")`）與 `request`，必要時在 `_build_items` 多傳一份未合併的 `plan_source`。

### 3C 後端（新增 `roi_distribution` action，可選但建議）
- `tauri_iso_workflow.py` 的 `_dispatch_request` 加 `if request.action == "roi_distribution": return roi_distribution(request)`，內部呼叫 `launcher/plugins/iso_tools/roi_calibration.py` 既有的 `confidence_distribution(rows, threshold=...)`。
- `isoWorkflow.ts` 加 wrapper `loadIsoRoiDistribution`；`RoiSamplePanel` 改吃後端結果（目前是前端用 `rows[].confidence` 估算，可保留為 fallback）。

### Batch 3 驗收
- 調校右欄出現可展開的 Pilot List（含 P13-P15），`engineer_detail`/`metrics` 顯示，`auto_fix`/前往按鈕可動。
- 改 ROI/threshold/sheet/col/pattern 後，調校頂端出現「草稿已過期」黃條。
- `tests/test_iso_pilot.py` 更新後通過（見 §5）。`-Suite frontend` 綠。Tauri UI 截圖（1181×790 + 最大化）。

---

## 4. 待辦 Batch 4 — 一鍵輕導引 / 失敗橋接（碰一鍵，務必小心）

`AutopilotView.tsx`（只加投影，不改 `runOneClick`/按鈕語意）：
- `IsoBoard` 傳 `pilotItems` 給 `AutopilotView`。
- pipeline 6 卡狀態改由 pilot 群組推導：來源=P01-P03、判讀=P06、對 ISO=P04/P07、命名=P10/P11、更名=P12（取群組中最差狀態著色）。目前是用 `oneClickStage` 粗推，改吃 pilot 後更準。
- 執行中標題列加一行「正在：<目前 running 的 pilot.user_text>」（job progress 已有 done/total）。
- 成功摘要用 `pilot_summary` 的人話（X 可更名 · Y 待確認），不出現 P 代號。
- 失敗時 `FailureCard` 再加一行「最可能原因」＝第一個 `blocked` pilot 的 `user_text`。
- **禁止**在一鍵出現 ROI / 下拉 / raw JSON / P 代號清單。

### Batch 4 驗收
一鍵 happy path 行為與 base 一致（全綠一路到底）；故意製造一個 blocked（例如改壞 pattern）→ 失敗卡顯示人話原因 + 既有三顆按鈕（複製/問題包/開工作台）。`-Suite frontend` 綠 + 一鍵 UI 截圖。

---

## 5. 待辦 Batch 5 — 測試 / polish

- `tests/test_iso_pilot.py`：
  - 既有 case 會因 P13-P15 加入而：`tuple(by_id)==PILOT_ITEM_IDS` 仍成立（兩邊都引用更新後的 `PILOT_ITEM_IDS`）；但 `report["summary"]["blocked"]==3` 等**計數斷言需重算**（P14 在該 sample 若無 missing 檔則非 blocked；P13/P15 預設非 blocked）。請依新項目重新核對期望值。
  - 新增：P15 `freshness=="stale"` 的觸發、P14 missing→blocked、blocks_apply 彙總。
  - 驗證 schema v2 欄位存在且預設安全（`freshness/needs_review/next_action`）。
- （可選）`stateMachine.ts` 的 apply guard 從「row 計數」改吃 pilot `blocks_apply` 彙總——**先寫對拍測試確認等價**再改，避免動到一鍵能否套用的判斷。
- 版面 polish：PilotStrip 在 1181×790 的換行、調校 Pilot List 高度、表格列高。

---

## 6. 驗證指令（你在 Windows 可全跑）

```
.\scripts\test.ps1 -Suite frontend          # = tsc && vite build
python -m pytest tests\test_iso_pilot.py tests\test_iso_one_click_workflow.py tests\test_iso_debug_bundle.py
.\scripts\test.ps1 -Suite tauri-ui          # 或 START_HERE > 5
# 進 ISO PDF → 工作台/調校 → 用 C:\Users\a0976\Downloads\t → 截圖 1181x790 與最大化
```

快速確認後端 pilot（純標準庫，免 PyQt/cv2）：

```python
from launcher.plugins.iso_tools.pilot import build_pilot_report, PILOT_ITEM_IDS, PILOT_SCHEMA_VERSION
r = build_pilot_report(request={"work_folder":"C:/x","detect_serials":True}, plan={"source":{}, "summary":{}, "rows":[], "issues":[]})
print(PILOT_SCHEMA_VERSION, len(r["items"]), [i["id"] for i in r["items"]])
```

---

## 7. 衝突情境對照（驗收時逐一確認，母文件 §4 有完整版）

| 情境 | 由哪個 Pilot 表達 |
|---|---|
| ROI 改過但草稿未重生 | P15 stale |
| Profile draft 與 published 不一致 | P14 warn |
| profile 指向已不存在的 PDF/ISO/page folder | P14 blocked |
| ISO List 換了但欄位 mapping 沿用舊值 | P05 warn + P15 stale |
| sheet 存在但 header 結構不同 | P04 / P05 |
| 影像判讀關閉但流程依賴流水號 | P06 / P13 |
| OCR 判讀值與 ISO List 對不上 | P07 |
| target filename 重複 | P08 |
| 使用者手動改 row 但未確認 | row：`note==="manual corrected"` → NamingTable「未確認」徽章（Batch 2 已做）；pilot 層可由 P11/P12 帶 `needs_review` |
| 一鍵可完成但有低信心列 | P06 warn + 一鍵 review gate |
| run log replay 與目前檔案狀態不同 | P15 stale |

---

## 8. 母文件與既有資產指引
- 設計總綱：`docs/iso_pdf_pilot_uplift_plan_2026-06-09.md`
- 三方統整與邊界裁決：`docs/iso_pdf_workbench_integrated_execution_plan_2026-06-08.md`
- 17 項 Pilot 細節（含 P13-P17 語意，注意編號錯位）：`docs/iso_pdf_next_stage_design_2026-06-08.md` §3.3
- 後端 Pilot 真相源：`launcher/plugins/iso_tools/pilot.py`、run log `run_log.py`、bundle `debug_bundle.py`、profile `profile.py`、ROI `roi_calibration.py`
- 前端 orchestrator：`frontend/tauri-spike/src/iso/IsoBoard.tsx`（state machine in `stateMachine.ts`）
