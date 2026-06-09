import { CircleAlert, CircleCheck, FileSearch, RefreshCcw, SearchCheck } from "lucide-react";
import type { IsoPlanRow, IsoPreviewPayload, IsoRegion } from "../../isoWorkflow";
import { RoiOverlay } from "./RoiOverlay";

export function IsoVisualPanel({
  activeRoi,
  adoptPreviewVision,
  busy,
  confirmSelectedRow,
  drawingRegion,
  editableRoi,
  error,
  nextProblem,
  preview,
  resetRoi,
  row,
  serialRegion,
  setActiveRoi,
  updateActiveRoi,
  updateRoi,
}: {
  activeRoi: "serial" | "drawing";
  adoptPreviewVision: () => void;
  busy: boolean;
  confirmSelectedRow: () => void;
  drawingRegion: IsoRegion;
  editableRoi: boolean;
  error: string;
  nextProblem: () => void;
  preview: IsoPreviewPayload | null;
  resetRoi: (region?: "serial" | "drawing") => void;
  row?: IsoPlanRow;
  serialRegion: IsoRegion;
  setActiveRoi: (region: "serial" | "drawing") => void;
  updateActiveRoi: (field: keyof IsoRegion, value: number) => void;
  updateRoi: (region: "serial" | "drawing", value: IsoRegion) => void;
}) {
  const activeRegion = activeRoi === "serial" ? serialRegion : drawingRegion;
  return (
    <div className="iso-visual-panel">
      <div className="panel-heading compact">
        <div>
          <span>PDF visual check</span>
          <small>{row?.source_name ?? "no page selected"}</small>
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
                  <span>{field}</span>
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
          <strong>{preview?.vision?.text ? `判讀：${preview.vision.text}` : "判讀：待確認"}</strong>
          <span>
            {preview?.vision
              ? `confidence ${Math.round(preview.vision.confidence * 100)}% · ${preview.vision.message || "no message"}`
              : busy
                ? "rendering"
                : error || "可用裁切圖人工確認流水號與圖號"}
          </span>
        </div>
      </div>
      <div className="row-review-actions">
        <button className="action-button" onClick={adoptPreviewVision} disabled={!preview?.vision?.text}>
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
