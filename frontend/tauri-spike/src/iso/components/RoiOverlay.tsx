import { useRef, type PointerEvent as ReactPointerEvent } from "react";
import type { IsoRegion } from "../../isoWorkflow";

type RoiTarget = "serial" | "drawing";

export function RoiOverlay({
  activeRoi,
  drawingRegion,
  editable,
  onChange,
  onSelect,
  serialRegion,
}: {
  activeRoi: RoiTarget;
  drawingRegion: IsoRegion;
  editable: boolean;
  onChange: (target: RoiTarget, region: IsoRegion) => void;
  onSelect: (target: RoiTarget) => void;
  serialRegion: IsoRegion;
}) {
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ target: RoiTarget; offsetX: number; offsetY: number; pointerId: number } | null>(null);

  function regionFor(target: RoiTarget) {
    return target === "serial" ? serialRegion : drawingRegion;
  }

  function pointFor(event: ReactPointerEvent<HTMLElement>) {
    const rect = overlayRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: clamp01((event.clientX - rect.left) / Math.max(1, rect.width)),
      y: clamp01((event.clientY - rect.top) / Math.max(1, rect.height)),
    };
  }

  function beginDrag(target: RoiTarget, event: ReactPointerEvent<HTMLDivElement>) {
    onSelect(target);
    if (!editable) return;
    event.preventDefault();
    const region = regionFor(target);
    const point = pointFor(event);
    dragRef.current = {
      target,
      offsetX: point.x - region.left,
      offsetY: point.y - region.top,
      pointerId: event.pointerId,
    };
    overlayRef.current?.setPointerCapture(event.pointerId);
  }

  function moveDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || !editable) return;
    const region = regionFor(drag.target);
    const point = pointFor(event);
    onChange(drag.target, {
      ...region,
      left: clamp(point.x - drag.offsetX, 0, 1 - region.width),
      top: clamp(point.y - drag.offsetY, 0, 1 - region.height),
    });
  }

  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    dragRef.current = null;
    overlayRef.current?.releasePointerCapture(event.pointerId);
  }

  return (
    <div
      className={`roi-overlay ${editable ? "editable" : "readonly"}`}
      onPointerCancel={endDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      ref={overlayRef}
    >
      <RoiBox
        active={activeRoi === "serial"}
        editable={editable}
        label="流水號 ROI"
        onPointerDown={(event) => beginDrag("serial", event)}
        onSelect={() => onSelect("serial")}
        region={serialRegion}
        tone="serial"
      />
      <RoiBox
        active={activeRoi === "drawing"}
        editable={editable}
        label="圖號 ROI"
        onPointerDown={(event) => beginDrag("drawing", event)}
        onSelect={() => onSelect("drawing")}
        region={drawingRegion}
        tone="drawing"
      />
    </div>
  );
}

function RoiBox({
  active,
  editable,
  label,
  onPointerDown,
  onSelect,
  region,
  tone,
}: {
  active: boolean;
  editable: boolean;
  label: string;
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onSelect: () => void;
  region: IsoRegion;
  tone: RoiTarget;
}) {
  return (
    <div
      aria-label={label}
      className={`roi-box ${tone} ${active ? "active" : ""} ${editable ? "editable" : ""}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      onPointerDown={onPointerDown}
      role="button"
      style={{
        left: `${region.left * 100}%`,
        top: `${region.top * 100}%`,
        width: `${region.width * 100}%`,
        height: `${region.height * 100}%`,
      }}
      tabIndex={editable ? 0 : -1}
    />
  );
}

function clamp01(value: number) {
  return clamp(value, 0, 1);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}
