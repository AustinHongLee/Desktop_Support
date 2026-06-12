import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { IsoRegion } from "../../isoWorkflow";

type LiveCropProps = {
  emptyText?: string;
  image?: string;
  region: IsoRegion;
  style?: CSSProperties;
};

export function LiveCrop({ emptyText = "等待預覽", image, region, style }: LiveCropProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [message, setMessage] = useState(image ? "" : emptyText);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image) {
      setMessage(emptyText);
      return;
    }
    let cancelled = false;
    let frame = 0;
    const bitmap = new Image();
    bitmap.onload = () => {
      if (cancelled) {
        return;
      }
      frame = window.requestAnimationFrame(() => {
        const context = canvas.getContext("2d");
        if (!context) {
          setMessage("無法建立裁切畫布");
          return;
        }
        const naturalWidth = bitmap.naturalWidth || bitmap.width;
        const naturalHeight = bitmap.naturalHeight || bitmap.height;
        const left = clamp01(region.left);
        const top = clamp01(region.top);
        const width = Math.max(0.01, clamp01(region.width));
        const height = Math.max(0.01, clamp01(region.height));
        const sx = Math.min(naturalWidth - 1, Math.max(0, Math.round(left * naturalWidth)));
        const sy = Math.min(naturalHeight - 1, Math.max(0, Math.round(top * naturalHeight)));
        const sw = Math.max(1, Math.min(naturalWidth - sx, Math.round(width * naturalWidth)));
        const sh = Math.max(1, Math.min(naturalHeight - sy, Math.round(height * naturalHeight)));
        canvas.width = sw;
        canvas.height = sh;
        context.clearRect(0, 0, sw, sh);
        context.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);
        setMessage("");
      });
    };
    bitmap.onerror = () => {
      if (!cancelled) {
        setMessage("裁切預覽載入失敗");
      }
    };
    bitmap.src = image;
    return () => {
      cancelled = true;
      if (frame) {
        window.cancelAnimationFrame(frame);
      }
    };
  }, [emptyText, image, region.height, region.left, region.top, region.width]);

  return (
    <div style={{ ...styles.shell, ...style }}>
      {message ? <span style={styles.message}>{message}</span> : null}
      <canvas ref={canvasRef} style={{ ...styles.canvas, opacity: message ? 0 : 1 }} />
    </div>
  );
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(1, Math.max(0, value));
}

const styles = {
  canvas: {
    display: "block",
    height: "auto",
    maxHeight: "100%",
    maxWidth: "100%",
    width: "auto",
  },
  message: {
    color: "rgba(220,235,228,0.58)",
    fontSize: 11,
    fontWeight: 850,
    left: "50%",
    position: "absolute",
    textAlign: "center",
    top: "50%",
    transform: "translate(-50%, -50%)",
    width: "90%",
  },
  shell: {
    alignItems: "center",
    background: "rgba(0,0,0,0.18)",
    display: "flex",
    height: 120,
    justifyContent: "center",
    minWidth: 0,
    overflow: "hidden",
    position: "relative",
    width: "100%",
  },
} satisfies Record<string, CSSProperties>;
