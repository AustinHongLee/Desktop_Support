# ISO PDF Node Workbench — 畫布 UI/UX V3 規格（Area / Page Item / ROI 同步）

> Date: 2026-06-11 ｜ Base: `codex/tauri-react-spike` @ `ba0a907`（其上 4 筆 ROI/預覽快取/試判 commit 仍是直上主線；V3 工作回分支 `codex/iso-workbench-uiux-v3`）
> 範圍：純前端畫布層（`workbench/`、`WorkflowCanvas.tsx`、`flowAdapter.ts` 呈現端）。零 backend、零 engine、零資料契約變更。
> **裁切不同步的根因已定位**：`NodeDetailPanel.tsx` L266-268 的裁切小圖用的是 `preview.serial_crop.image` / `drawing_crop.image`——**後端上次渲染的 crop**；拖 ROI 時前端 overlay 即時動、後端 crop 要等 debounce 回傳（且 `f7a2bd2` 的 per-page 快取會讓舊圖更久）。V3 用前端即時裁切根治（§3/§4）。

> Codex 施工修正：本專案目前產品目標是「每個 PDF/page 可各自調校 ROI」。下方原稿若提到 ROI 收斂回全域，視為不採用；V3 實作需保留 per-page ROI draft，並讓每個 Page Item 自己持有裁切預覽、試判結果與 dirty 狀態。

---

## 1. 畫布分區（Area，五區固定）

```text
┌─來源區─┐ ┌─ISO 清單區─┐ ┌─PDF 分割區─┐ ┌────頁面處理區（最寬）────┐ ┌─輸出/更名區─┐
│ 工作區  │ │ ISO 清單   │ │ 合併 PDF   │ │ PageItem 1（可展開）      │ │ Pilot/結果表 │
│        │ │ 工作表     │ │ 分割工具    │ │ PageItem 2               │ │ 匯出 CSV 🔒 │
│        │ │ 欄位設定   │ │ （全域 ROI  │ │ PageItem 3 …             │ │ 套用更名 🔒 │
│        │ │ 命名格式   │ │  摘要徽章） │ │ [+N 頁…]                 │ │             │
└────────┘ └───────────┘ └───────────┘ └─────────────────────────┘ └────────────┘
   x=0        x=320          x=660          x=1020                     x=2240
```

- Area = React Flow **group node**（`type:"area"`）：半透明底色+左上標題+圓角框；`selectable:false`、`draggable:false`、zIndex 最低。寬度固定（頁面處理區 1140px，其餘 280-320px），高度隨內容計算。
- 區間水平 gutter 60px（走線通道）；區內 padding 24px；連線只允許「右出左進、跨相鄰區」（rows→輸出區為唯一跨兩區長線，走底部通道）。

## 2. Page Item 設計（頁面處理區的基本單位）

每頁一個 **PageItem group**（`parentId`=頁面處理區、自身又是 4 張卡的 parent），內含固定橫排：

```text
┌─ 頁 3 ──────────────────────────────────────────────── [收合 ▾] ─┐
│ ┌Page source┐→┌ROI 調校(本頁視圖)┐→┌判讀結果┐→┌命名合成┐         │
│ │ 240×200   │ │ 460×560          │ │ 260×200 │ │ 260×160 │        │
│ │ 縮圖+頁碼  │ │ §3 規格          │ │ serial/ │ │ 新檔名/  │        │
│ │ 檔名      │ │                  │ │ conf/狀態│ │ 衝突    │        │
│ └───────────┘ └──────────────────┘ └─────────┘ └─────────┘        │
└──────────────────────────────────────────────────────────────────┘
展開尺寸：1100×620（含 24px 內距、卡間 28px）｜收合尺寸：1100×64
收合列內容：頁碼｜48px 縮圖｜serial（或「未判讀」）｜conf 膠囊｜狀態點｜[展開]
```

- 卡片全部 `draggable:false` + `extent:"parent"`：PageItem 內部是**鎖定排版**，使用者只能拖整個 PageItem 不能拖散卡片（PageItem 本身也建議鎖定，僅畫布平移縮放）。
- PageItem 垂直間距 32px；同時展開上限 **3 個**（再展開第 4 個 → 最早展開的自動收合，LRU）；點收合列任意處=展開。
- **ROI 參數是 per-page item state**（採用 `ba0a907` 的 per-page isolation）：每頁 ROI 卡是該 PDF/page 的獨立框選視圖；任何一頁改框 = 只標記該頁與該頁下游結果 dirty。批次重跑若暫時只能吃全域 engine input，前端仍不得把 per-page draft 收斂回全域；需以「本頁試判」與「結果過期」標示保留使用者意圖。

## 3. ROI 調校卡正確互動（460×560）

```text
┌🎯 ROI（本頁視圖）── 頁 3 ──●┐
│ 主圖 412×~380（fit 寬、上限高）│ ← 完整頁 + RoiOverlay 兩框（藍=流水號、紫=圖號），拖曳即時
│ 裁切：[流水號▣] [圖號▣]      │ ← §4 前端即時裁切，與主圖框「定義上同源」永不脫鉤
│ 門檻 ──●── 0.70  偵測[on]    │
│ 試判：A123 (0.92) ✓ / —      │
│ [判讀此頁] [重跑下游 ⚠48頁]   │ ← 「只更新預覽」按鈕移除：預覽本來就即時，不需要按
└─────────────────────────────┘
```

- 主圖：沿用已載入的整頁 base64（`loadIsoPreview` 取一次、per-page 快取 OK）；overlay 框拖動只改 overlay state。
- **slider/拖框期間：零 `loadIsoPreview(detect)`、零 OCR、零 OpenCV、零 backend**——裁切小圖由前端算（§4），整頁底圖不需重取，所以連 debounced 預覽請求都省了；唯一觸發後端的是兩顆按鈕。
- 「判讀此頁」= 既有單頁判讀路徑（`loadIsoPreview` + `detect_serial:true`），回填「試判」列 + `pageTrials[page]`（前端暫存）；「重跑下游」= 既有 `workflow_run_from`（batch_detect 起），按鈕標註頁數成本。
- 判讀結果卡顯示的 serial/drawing **後端 crop**（OCR 實際看到的證據圖）與本卡前端 crop 是兩種東西：本卡=「現在框到什麼」，結果卡=「上次判讀看到什麼」。

## 4. 裁切預覽策略（根治不同步）

1. **前端即時裁切**：`<canvas>` `drawImage(pageImg, sx, sy, sw, sh, 0, 0, dw, dh)`，其中 `sx = region.left × naturalWidth` 等比換算；ROI overlay 與 crop 小圖讀**同一個** region state → 定義上同步，根除 race。實作為 `workbench/LiveCrop.tsx`（props: image, region, height=64）；requestAnimationFrame 節流即可，無需 debounce。
2. **後端 crop 的角色降級**：`preview.serial_crop/drawing_crop` 不再出現在 ROI 卡；只在「判讀結果卡」與 inspector 證據區顯示，標題改「判讀時擷取」。
3. **dirty 過期標示**：每次單頁試判/批次判讀完成時快照 `roiAtDetection`；當前 region ≠ 快照 → 判讀結果卡與命名合成卡掛琥珀膠囊「結果基於舊 ROI」、後端 crop 圖降飽和 40% + 斜紋角標；按「判讀此頁/重跑下游」成功後清除。

## 5. React Flow 實作建議

| 題目 | 裁決 |
|---|---|
| Area 用什麼 | **group node**（`type:"area"`，自訂渲染半透明框+標題）；不要用背景 div 疊圖（會跟縮放脫節） |
| Page Item | group node、`parentId`=頁面處理區 area、`extent:"parent"`；4 張卡 `parentId`=PageItem、座標寫死（fixed layout 函式統一計算，無 auto-layout 套件） |
| 邊 routing | `type:"smoothstep"` + `pathOptions.offset=16`；handle 固定右出左進；跨區線走 gutter；PageItem 內部卡間「→」不用真 edge，用卡片間 16px 箭頭圖示（減少 edge 數量與纏線） |
| 防 overlap | 全部位置由單一 `layoutWorkbench()` 純函式輸出（區 x 固定、區內 y 累加各卡高+間距）；展開/收合只改該 PageItem 高度並重算其下方 y；禁止任何 `position` 殘留舊值 |
| 前 10 頁與展開 | 沿用 v2 規則（前 10 ∪ 低信心 ∪ 未判讀，上限 20 個 PageItem render，其餘進「+N 頁…」S 卡，每按 +20）；收合列輕（64px），展開上限 3（LRU）；`onlyRenderVisibleElements` 開啟；縮圖 lazy + LRU 24 |
| 效能 | PageItem 收合時不掛 LiveCrop/canvas；React.memo 卡片、selector 化 summary 計算 |

## 6. 明確不要做

不重構 workflow backend / engine / 資料契約；不引入新 graph/layout 套件（dagre/elk 都不要，layout 是純函式）；不改一鍵/工作台/調校三分頁；不在 slider/拖框觸發任何 backend；不一次 render 全部頁；匯出/套用維持 🔒 既有確認路徑；不做接線編輯、佈局持久化、未來幻想功能；`.qwen/` 不碰。

## 7. 施工順序（V3-1 ~ V3-4，每步一 commit）

| 步 | 內容 | 驗收 |
|---|---|---|
| V3-1 | `LiveCrop.tsx` + ROI 卡改前端裁切、移除「只更新預覽」、後端 crop 移到結果卡；ROI state 收斂回全域單一事實 | 拖框時主圖框與裁切圖逐幀一致；DevTools 拖 30 次零 backend 請求；改任一頁框→所有頁結果卡標 dirty |
| V3-2 | `layoutWorkbench()` 五區 Area group + 固定座標；邊 routing 規則 | 五區框可見、零卡重疊、線右出左進不穿卡 |
| V3-3 | PageItem group（展開/收合、4 卡鎖定排版、LRU 3 展開、收合列） | 48 頁 fixture：初始 ≤20 個 item、展開第 4 個時最舊自動收合、拖 PageItem 不散架 |
| V3-4 | dirty 過期視覺（§4.3）+ 效能（memo/visible-only/縮圖 LRU）+ 驗收清單全跑 + docs postscript + merge/tag `iso-workbench-uiux-v3` | 200 頁 fixture 首繪 <2s、平移縮放不掉幀（目測 >30fps）；下方 Acceptance 全勾 |

每步驗證：`cd frontend\tauri-spike; npx tsc --noEmit; npm run build; npm run test:unit`；V3-4 加 `python -m pytest tests\test_frontend_safety_contract.py tests\test_iso_workflow_pollution.py -q` 與 full pytest。

## 8. Acceptance Criteria（V3-4 逐項打勾）

- [ ] 拖動 ROI 框/slider 時，裁切小圖與主圖框即時一致（無一幀落差感）、且零 OCR/backend 請求。
- [ ] 只有「判讀此頁」觸發單頁判讀、只有「重跑下游」觸發 batch；兩按鈕外無任何執行入口。
- [ ] ROI 變更後，所有頁的判讀結果/命名合成卡出現「結果基於舊 ROI」標示；重判後消失。
- [ ] 五個 Area 視覺清楚，卡片不重疊、不可拖出區外，線路一律左→右。
- [ ] 每頁是一個完整 Page Item（source→ROI→結果→合成），可展開/收合，同時展開 ≤3。
- [ ] 預設只 render 前 10 頁∪低信心∪未判讀（≤20），「+N 頁」可逐步展開；200 頁不卡。
- [ ] 匯出/套用仍為 🔒 確認制；一鍵/工作台/調校零變化；既有測試 0 failed。

---

**給 Codex 短版命令**：讀本文件 → `git switch codex/tauri-react-spike && git pull --ff-only && git switch -c codex/iso-workbench-uiux-v3` → 先 commit 本規格 → 照 V3-1→V3-4 施工，每步一 commit+push+驗收；只動前端畫布層，engine/契約/policy/三分頁零修改；卡關停下寫短報告。完成 → merge --no-ff + tag `iso-workbench-uiux-v3` + 停工回報（全景截圖 + 上方 checklist 勾選表）。
