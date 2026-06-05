# Codex 指令書:ISO PDF 一鍵命名工作台 — 重做(好看 + 快 + 資料正確)

> 目標一句話:把新版 Tauri ISO 工作台重做得**好看、快、資料正確**。三個模式:**一鍵**(給完全不懂的人,一顆按鈕到底)、**工作台**(逐列校對)、**調校**(工程師)。前一版已能編譯但「介面糟、資料糟、處理慢」,請以下面規格重做。

---

## 1. 專案與架構(先讀懂再動)

- 前端:`frontend/tauri-spike/`(React + Vite + Tauri)。主檔 `src/App.tsx`、`src/isoWorkflow.ts`、`src/styles.css`。
- 後端橋接(Python,被 Tauri 以子程序呼叫):
  - `launcher/app/tauri_iso_workflow.py` — actions:`plan / apply / export_plan_csv / start_batch_detect / job_status / cancel_job / load_profile / save_profile` …
  - `launcher/app/tauri_iso_worker.py` — 批次判讀 worker(逐頁寫進度到 `job.json`,前端輪詢)。
  - `launcher/app/tauri_iso_preview.py` — 單頁 PDF 預覽 + 裁切 + 判讀。
- 純邏輯層(**不要在前端重刻**,呼叫同一條):`launcher/plugins/iso_tools/`(`iso_naming` 載 ISO/拆頁/命名、`serial_vision` OCR+OpenCV 判讀、`serial_correction` 對 ISO 校正、`profile` 持久化、`rename_plan`)、`launcher/plugins/rename_tools/rename_actions.py`(staged rename + rollback,已穩,沿用)。
- Tauri commands:`frontend/tauri-spike/src-tauri/src/main.rs`(`run_iso_workflow`、`preview_iso_pdf_page`、`pick_*`)。
- 資料流:`invoke` → Rust `spawn python -m launcher.app.tauri_iso_workflow` → 讀 stdin JSON → 印 stdout JSON → 行程結束。批次判讀走 job 檔輪詢。

---

## 2. 「慢」的根因 + 怎麼修(效能,最高優先)

1. **每個動作都 spawn 新 Python,冷啟動 import PyQt6 + opencv + RapidOCR(每次數秒)。**
   - 對策(擇一,(a) 最佳):(a) 改成**常駐 sidecar / 長壽命後端**,OCR 模型只載一次、重複服務請求(Tauri sidecar 或本機 socket/stdin-loop);(b) 至少把 heavy import 全部 lazy,且批次 job 內 **RapidOCR 只 new 一次**重複用。
2. **逐頁 OCR 慢。** → `QThreadPool` / multiprocessing 並行(上限可設,別燒 CPU);render 解析度自適應;對相同頁面(image hash)快取判讀結果。
3. **輪詢 0.9s 有延遲感。** → 縮到 ~300–400ms,或改用 Tauri event 推送進度取代輪詢。
4. **量測並附數據**:`python -X importtime` 看冷啟動;記一批 60 頁的判讀總秒數作前後基準。

---

## 3. 資料正確性規則(這些是上一版的真 bug,別再踩)

- 判讀**成功**(信心 ≥ 門檻、流水號在 ISO List)→ `status = ready` 且該列 **auto-selected**;判讀訊息放 `vision_message`,**不要當 warning note**(否則每列都變 warn、一鍵直接卡死)。
- 低信心 / ISO 無此號 → 退回頁序,`status = warn`,但**仍 auto-selected**(只標黃供複核)。
- 無法命名(缺圖號、檔名重複、目標已存在、非法字元)→ `status = blocked`,不選取。
- 套用後**不要同步重跑整批 OCR**(會凍 UI);本地移除已更名列即可。
- 命名表要能在固定高度內**捲動**(60+ 列不可把整頁撐長)。
- **每次套用自動寫一份 CSV 記錄**(原檔名→新檔名、流水號、信心、狀態、`vision_message`、來源/目標完整路徑、時間)到頁面資料夾,供工程師事後核對與**反向救援**。後端 `export_plan_csv` 已有,直接用。

---

## 4. 三個模式 UX 規格

### 4.1 一鍵(Autopilot)— 給完全不懂的人
- 整區**只有一顆按鈕** + 一條 **card-and-arrow 管線** + 底部**終端機 echo**。**不要** PDF 預覽、不要 ROI、不要一堆確認按鈕。
- 按鈕狀態機:沒資料夾→「選擇工作資料夾」;選好→「開始一鍵命名」;跑中→「判讀中 N/M · Xs」(可取消);**全綠→自動更名到底,不跳任何確認**;有低自信→停在 review,按鈕變「我已確認,更名 N 筆」。
- 管線六節點:`來源 → 拆頁 → 判讀流水號 → 對 ISO → 命名 → 更名`;當前節點發亮並顯示**運算秒數**,完成打勾。
- 終端機:底部固定,逐頁 echo 事件(slowly running 的感覺),帶計時與閃爍游標。**不要假進度**,要吃 worker 真實事件。
- 低自信才停:用 pilot checklist 把要確認的幾列攤出來;點一列可跳到工作台該列修。
- 結束:顯示「完成 · 已更名 N 筆 · 記錄:<路徑>」。

### 4.2 工作台(Workbench)— 逐列校對
- 來源 / ISO 設定(可收合)+ 命名表(主,可捲動;含全選、只看問題、搜尋、信心欄、狀態多色高亮)+ 右側 PDF 預覽與裁切。
- 從頭到尾也要有 pilot checklist(起飛前 / 落地前)。

### 4.3 調校(Engineer)— 工程師
- ROI 拖框(流水號 / 圖號)、信心門檻、ISO 欄位對應、命名 template、Profile 存取、OCR 設定。
- 從頭到尾也要有 checklist。

---

## 5. 美術方向(放手發揮,守住這些)
- 深色 cockpit 風:主色 neon 青綠 `#2ff5c8`、警示琥珀 `#ffd166`、危險紅;扁平、低視覺噪音、留白足。
- 一鍵那頁要**一眼就懂怎麼按**;管線 + 終端機要有「機器在運轉」的高級感,但**不准假動畫**。
- 版面與配色可自由重排,只要符合上面 UX 與資料規則。

---

## 6. 驗收標準
- 一鍵:選資料夾 → 一顆按鈕 → 全綠自動更名完成、有低自信才停;管線逐階段亮 + 秒數;終端機逐行 echo;頁面資料夾出現 CSV 記錄。
- 不再出現:「判讀成功卻全 warn 卡住」「套用後當掉」「命名表太長不捲」。
- 一批 60 頁判讀時間有改善(附前後秒數)。
- `npm run build` / `tsc --noEmit` 乾淨;`python -m py_compile` 後端乾淨;`python -m unittest discover tests` 不回歸。

---

## 7. 注意事項
- **別在前端重刻**判讀 / 命名 / 驗證邏輯,呼叫 `plugins/iso_tools` 同一條 pipeline,避免兩邊規則漂移。
- 別為了好看加假進度條 / `setTimeout` 假裝 async。
- 改檔請用 type hints、`from __future__ import annotations`、logging(勿 print)。
- 動工前先跑一次現況、記錄基準秒數;完成後輸出:變更檔清單 + 怎麼跑 + 前後效能數字。

---

## 8. 背景補充(可參考的既有分析)
專案 `docs/` 內已有更深的分析可參考:`iso_pdf_workbench_audit.md`、`iso_pdf_workbench_next_stage_v0.1.md`(Autopilot + Workbench + checklist + undo + engineer mode 的完整藍圖)、`ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md`(新舊落差盤點與 UI 重分配)。沿用其方向即可,不必從零設計。
