import { CircleAlert, CircleCheck, FileSearch, RefreshCcw, SearchCheck } from "lucide-react";
import type { IsoPlanRow, IsoPreviewPayload, IsoRegion } from "../../isoWorkflow";
import { RoiOverlay } from "./RoiOverlay";

export function IsoVisualPanel({
  activeRoi,
  adoptPreviewVision,
  busy,
  confidenceThreshold,
  confirmSelectedRow,
  detectSerials,
  drawingRegion,
  editableRoi,
  error,
  nextProblem,
  preview,
  previewPending,
  resetRoi,
  row,
  serialRegion,
  setConfidenceThreshold,
  setActiveRoi,
  setDetectSerials,
  updateActiveRoi,
  updateRoi,
}: {
  activeRoi: "serial" | "drawing";
  adoptPreviewVision: () => void;
  busy: boolean;
  confidenceThreshold: number;
  confirmSelectedRow: () => void;
  detectSerials: boolean;
  drawingRegion: IsoRegion;
  editableRoi: boolean;
  error: string;
  nextProblem: () => void;
  preview: IsoPreviewPayload | null;
  previewPending: boolean;
  resetRoi: (region?: "serial" | "drawing") => void;
  row?: IsoPlanRow;
  serialRegion: IsoRegion;
  setConfidenceThreshold: (value: number) => void;
  setActiveRoi: (region: "serial" | "drawing") => void;
  setDetectSerials: (value: boolean) => void;
  updateActiveRoi: (field: keyof IsoRegion, value: number) => void;
  updateRoi: (region: "serial" | "drawing", value: IsoRegion) => void;
}) {
  const activeRegion = activeRoi === "serial" ? serialRegion : drawingRegion;
  const roiFieldLabels: Record<keyof IsoRegion, string> = {
    left: "左距",
    top: "上距",
    width: "寬度",
    height: "高度",
  };
  return (
    <div className="iso-visual-panel">
      <div className="panel-heading compact">
        <div>
          <span>PDF 視覺檢查</span>
          <small>{row?.source_name ?? "尚未選擇頁面"}</small>
        </div>
      </div>

      <div className={`pdf-page-frame ${preview ? "ready" : ""}`}>
        {preview ? (
          <div className="pdf-page-canvas">
            <img src={preview.page.image} alt={`PDF preview ${preview.source_name}`} />
            <RoiOverlay
              activeRoi={activeRoi}
              drawingRegion={drawingRegion}
              editable={editableRoi}
              onChange={updateRoi}
              onSelect={setActiveRoi}
              serialRegion={serialRegion}
            />
          </div>
        ) : (
          <div className="pdf-preview-empty">
            <FileSearch size={26} />
            <span>{busy ? "載入 PDF 預覽中" : error || "選擇命名列後顯示 PDF 預覽"}</span>
          </div>
        )}
      </div>

      <div className="roi-panel">
        <div className="segmented mini">
          <button className={activeRoi === "serial" ? "active" : ""} onClick={() => setActiveRoi("serial")}>流水號 ROI</button>
          <button className={activeRoi === "drawing" ? "active" : ""} onClick={() => setActiveRoi("drawing")}>圖號 ROI</button>
        </div>
        {editableRoi ? (
          <>
            <div className="roi-controls">
              {(["left", "top", "width", "height"] as Array<keyof IsoRegion>).map((field) => (
                <label className="roi-slider" key={field}>
                  <span>{roiFieldLabels[field]}</span>
                  <input
                    max={field === "left" || field === "top" ? 0.95 : 1}
                    min={field === "width" || field === "height" ? 0.05 : 0}
                    onChange={(event) => updateActiveRoi(field, Number(event.target.value))}
                    step="0.01"
                    type="range"
                    value={activeRegion[field]}
                  />
                  <strong>{activeRegion[field].toFixed(2)}</strong>
                </label>
              ))}
            </div>
            <button className="action-button" onClick={() => resetRoi()}>
              <RefreshCcw size={14} />
              <span>重設目前 ROI</span>
            </button>
            <div className="roi-threshold-control">
              <div>
                <span>信心門檻</span>
                <strong>{Math.round(confidenceThreshold * 100)}%</strong>
              </div>
              <input
                max="0.99"
                min="0.1"
                onChange={(event) => setConfidenceThreshold(Number(event.target.value))}
                step="0.01"
                type="range"
                value={confidenceThreshold}
              />
            </div>
            <label className="roi-detect-toggle">
              <input type="checkbox" checked={detectSerials} onChange={(event) => setDetectSerials(event.target.checked)} />
              <span>影像判讀流水號</span>
            </label>
          </>
        ) : (
          <div className="roi-readonly-note">
            <strong>ROI 只讀</strong>
            <span>調校模式更新草稿框線</span>
          </div>
        )}
      </div>

      <div className="pdf-crop-grid">
        <PreviewCrop title="右上流水號" image={preview?.serial_crop.image} />
        <PreviewCrop title="右下圖號" image={preview?.drawing_crop.image} />
      </div>

      <div className="vision-readout">
        <SearchCheck size={15} />
        <div>
          <strong>{previewPending ? "判讀：等待重新判讀" : preview?.vision?.text ? `判讀：${preview.vision.text}` : "判讀：待確認"}</strong>
          <span>
            {previewPending
              ? "ROI 調整中，停止滑動後重新產生裁切與判讀"
              : preview?.vision
              ? `信心 ${Math.round(preview.vision.confidence * 100)}% · ${preview.vision.message || "無訊息"}`
              : busy
                ? "產生預覽中"
                : error || "可用裁切圖人工確認流水號與圖號"}
          </span>
        </div>
      </div>
      <div className="row-review-actions">
        <button className="action-button" onClick={adoptPreviewVision} disabled={previewPending || !preview?.vision?.text}>
          <SearchCheck size={14} />
          <span>採用判讀值</span>
        </button>
        <button className="action-button" onClick={confirmSelectedRow} disabled={!row}>
          <CircleCheck size={14} />
          <span>確認此列</span>
        </button>
        <button className="action-button" onClick={nextProblem}>
          <CircleAlert size={14} />
          <span>下一問題</span>
        </button>
      </div>
    </div>
  );
}

function PreviewCrop({ image, title }: { image?: string; title: string }) {
  return (
    <div className="preview-crop">
      <span>{title}</span>
      {image ? <img src={image} alt={title} /> : <div />}
    </div>
  );
}
