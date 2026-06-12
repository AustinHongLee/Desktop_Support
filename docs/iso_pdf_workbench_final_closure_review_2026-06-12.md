# ISO PDF Node Workbench — 最終收斂審查與收尾清單

> Date: 2026-06-12 ｜ Branch: `codex/iso-workbench-uiux-v3` @ `875a601`（12 筆 V3 commit 已在分支，含 LiveCrop 同步、PageItem、workspace card、apply action card、背板移除）
> 性質：收尾判斷，不是新階段。⚠ 沙箱視圖顯示 3 份 docs 為 M——大概率是已知的掛載截斷假象，Windows 端先 `git status` 確認；若檔案尾端真的缺損，`git restore` 還原，**不要**把截斷版 commit 進去。

## 1. 最終判斷

**接近可收尾。** 引擎、安全層、執行鏈、畫布主體都在；剩下的是 3 個 P0（語意正確性）+ 4 個 P1（完成度），合計 7 項、預估 1-2 個工作天。沒有任何一項需要重構或新框架。P2/漂亮化/進階互動全部進 §6 停止條款。

## 2. 最後必修清單（7 項，P0 先做）

| # | 級 | 問題 | 為什麼阻礙收尾 | Codex 改的方向 | 驗收 |
|---|---|---|---|---|---|
| 1 | P0 | **每頁 ROI Card 與批次判讀的參數語意可能分裂**：每頁有自己的 ROI 卡，但引擎 batch_detect 只吃一組全域 region。若卡片各存各的框，使用者調了頁 5、批次卻用別組框＝結果與所見不符 | 所見非所得=使用者無法信任流程 | 收斂為全域單一事實：任一頁卡改框→寫同一組全域 region→全部頁標 dirty；卡上加一行「ROI 為全部頁共用」。若要保留每頁試判彈性，僅 `pageTrials` 暫存可以 per-page | 改頁 3 的框→頁 7 的結果卡同步出現「結果基於舊 ROI」；重跑下游後批次結果與頁 3 試判一致 |
| 2 | P0 | **dirty→重跑鏈要閉環**：ROI/欄位/格式變更後，「結果基於舊 ROI/參數」標示與「重跑下游」入口必須一路通到 Pilot/匯出/套用卡 | 使用者拿舊結果去套用更名=實際風險 | 沿 V3-4 規格補齊 roiAtDetection 快照比對；套用更名卡在 dirty 時按鈕降級為「先重跑下游」 | dirty 狀態下套用卡不可直接套用；重跑完成後恢復 |
| 3 | P0 | **收尾回歸全綠**：分支上未證明 full pytest / pollution / safety contract / tsc / build / test:unit 全綠 | 不綠就 merge=把未知債帶回主線 | 跑全矩陣，紅的修到綠（僅限修測試所揭示的 bug，不擴大） | `python -m pytest tests -q` 0 failed；前端三件套綠 |
| 4 | P1 | **空狀態與錯誤人話**：未選工作區/缺 ISO 清單/缺 PDF 時，畫布要有「從這裡開始」引導與一句人話，不能一片灰卡 | 新使用者第一步就卡死 | 工作區卡空狀態=唯一亮起+引導文案；缺檔時對應卡琥珀「請選擇…」 | 開空資料夾走一遍，每一步都知道下一步按哪 |
| 5 | P1 | **匯出/套用確認制在畫布內的最終驗證**：action card 直觸既有受控流程（ac8d73f），需證明確認對話框、`.runtime/exports` 路徑、apply record artifact 都未被繞過 | 安全契約是本專案底線 | 不改碼，跑 pollution+safety contract+人工各一次；有繞過即修 | 匯出落 `.runtime/exports/iso/`；套用必經確認框；工作資料夾零 `iso_rename_plan_*.csv` |
| 6 | P1 | **頁數效能驗收未做**：V3-4 的 200 頁 fixture 首繪 <2s、展開上限 3 LRU、縮圖 LRU 未驗 | 真實 48+ 頁樣本會直接撞上 | 開 `onlyRenderVisibleElements`（若未開）、補一次 200 頁 fixture 實測並記數字 | 200 頁首繪 <2s、平移不掉幀、同時展開 ≤3 |
| 7 | P1 | **合流收尾**：分支 merge + tag + docs postscript；工作樹上 3 份疑似截斷的 docs 要先核實 | 不合流=又一條長壽分支 | Windows 核實 docs → `git merge --no-ff` 回 `codex/tauri-react-spike` → tag `iso-workbench-uiux-v3` → 刪本地分支 → 本文件 append 完工註記 | `git log --graph` 見 merge；tag 已 push |

## 3. 最終節點式使用流程（使用者視角 × 承擔 Card）

1. **選工作區**→「選取工作區」卡（來源區）：點選資料夾，卡上三勾（合併 PDF ✓ / ISO 清單 ✓ / 拆頁 ✓✗）。
2. **載入 ISO 與 PDF**→「ISO 清單」「合併 PDF」卡自動帶出探索結果；不對就卡上換檔。
3. **確認表格**→「工作表」「欄位設定」「命名格式」卡：sheet/欄位下拉、格式示例即時渲染。
4. **分割 PDF**→「分割工具」卡：按「開始整理/重新拆頁」，完成顯示頁數。
5. **預覽 ISO/拆頁**→各卡縮圖與樣本列（已修垂直重疊）。
6. **每頁 ROI 調校**→PageItem 內 ROI 卡：拖框即時 LiveCrop，「判讀此頁」看試判。
7. **批次判讀**→「判讀結果」卡或 ROI 卡「重跑下游」：進度條+四計數。
8. **Pilot 檢查**→「Pilot/結果表」卡：P01-P15 三色膠囊，問題開 inspector。
9. **匯出 CSV**→「匯出 CSV」卡 🔒：確認後落 `.runtime/exports/iso/`。
10. **套用更名**→「套用更名」卡 🔒：dirty 時禁用；確認框→更名→record artifact。

## 4. 最小人工驗證腳本（樣本 `C:\Users\a0976\Downloads\t`，建議先複製一份副本操作）

1. 開節點式分頁 → 預期：大畫布、工作區卡亮起引導。
2. 工作區卡選 `Downloads\t 副本` → 預期：三勾亮、ISO 清單卡顯示 HP6 xlsx、合併 PDF 卡顯示 testing.pdf。
3. 分割工具卡按拆頁 → 預期：頁數出現、頁面處理區長出 PageItem（4 頁樣本全展示）。
4. 展開頁 1 ROI 卡，拖流水號框 10 次 → 預期：裁切小圖逐幀跟動、DevTools 無任何判讀請求。
5. 按「判讀此頁」→ 預期：3 秒內試判列顯示 serial+信心。
6. 改框後看頁 2-4 → 預期：結果卡全部出現「結果基於舊 ROI」。
7. 按「重跑下游」→ 預期：判讀結果卡進度跑完、4 列、dirty 標示消失、Pilot 卡 P01-P15 計數（期望 4 ready）。
8. 匯出 CSV 卡 → 確認框 → 預期：訊息含 `.runtime\exports\iso\` 完整路徑；副本資料夾內**沒有**新 CSV。
9. 套用更名卡 → 確認框 → 套用 → 預期：副本內 4 個 PDF 改名成 `{serial}--{line}.pdf`；再開 run log drawer 可見 apply 紀錄。
10. 切到一鍵/工作台/調校分頁 → 預期：行為與改版前完全相同。

## 5. Codex 最終施工順序

1. 修 #1 全域 ROI 語意（前端 state 收斂，一 commit）。
2. 修 #2 dirty 閉環＋套用卡降級（一 commit）。
3. 補 #4 空狀態引導（一 commit）。
4. 開 #6 效能項＋200 頁實測記錄（一 commit）。
5. 跑 #3/#5 全矩陣與人工腳本（§4），紅修到綠（修復各自小 commit）。
6. #7 合流：核實 docs → merge --no-ff → tag `iso-workbench-uiux-v3` → push → 本文件 append 完工註記。

## 6. 停止條款（現在不要做）

不開新階段/新施工書；不做 React Flow 進階互動（接線編輯、佈局保存、動畫美化、minimap 客製）；不做視覺重設計；不加新節點類型；不為未來可能性加任何抽象層；不動 workflow engine/policy/契約（除非 #3 揭露 P0 bug）；不取代一鍵/工作台/調校；不優化 worker/OCR 效能；`.qwen/` 不碰；不用 `git add -A`。

---

**給 Codex 的一句話：照 §5 做完 1-6 並讓 §4 腳本與全測試矩陣通過後，節點式工作流即視為第一版完成（v1 done），合流打 tag 後停工，不要再開下一階段。**

---

## 7. Codex 收尾紀錄（2026-06-12）

- P0 #1/#2 已完成：`c6eeb32 fix(iso-workbench): close roi dirty rerun loop`
  - ROI 改為全域單一事實；任一頁 ROI 卡變更會寫回全域 ROI/門檻。
  - ROI 變更會清除舊試判、標記整條 batch/pilot/export/apply 鏈 dirty。
  - ROI 卡顯示「ROI 為全部頁共用」。
  - 結果卡 dirty 時顯示「結果基於舊 ROI/參數，請先重跑下游」。
  - 匯出/套用卡 dirty 時按鈕降級為「先重跑下游」，不直接匯出或套用。
- P1 #4 已完成：`31a688c fix(iso-workbench): clarify empty canvas states`
  - 未選工作區、缺 ISO、缺合併 PDF、尚未拆頁時，對應卡片會提示下一步。
- 回歸驗證：
  - `npm run build`：通過。
  - `npm run test:unit`：4 passed。
  - `python -m pytest tests -q`：487 passed。
  - `python -m pytest tests/test_frontend_safety_contract.py tests/test_iso_workflow_pollution.py tests/test_iso_workflow_apply_safety.py -q`：25 passed。
  - 200 頁 synthetic workspace 後端煙霧測試：200 rows completed，約 0.992s，工作區 `iso_rename_plan_*.csv` 數量 0。
  - 前端畫布仍維持 `PAGE_CHUNK_SIZE = 10` 且 `onlyRenderVisibleElements` 開啟。
- 待收尾：
  - 合流 `codex/iso-workbench-uiux-v3` → `codex/tauri-react-spike`。
  - 打 tag `iso-workbench-uiux-v3`。
