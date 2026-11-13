import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import type { Layer, Panel } from "../types";
import { PANEL_SIZE } from "../types";

const SCALE = 4;
const MIN_SIZE = 2;
const MAX_SIZE = PANEL_SIZE * 2;

type Corner = "nw" | "ne" | "sw" | "se";

const CORNERS: { dir: Corner; style: CSSProperties; cursor: string }[] = [
  { dir: "nw", style: { left: -5, top: -5 }, cursor: "nwse-resize" },
  { dir: "ne", style: { right: -5, top: -5 }, cursor: "nesw-resize" },
  { dir: "sw", style: { left: -5, bottom: -5 }, cursor: "nesw-resize" },
  { dir: "se", style: { right: -5, bottom: -5 }, cursor: "nwse-resize" },
];

interface Props {
  panel: Panel;
  preview: string | undefined;
  selectedLayerId: string | null;
  onSelect: (layerId: string | null) => void;
  onLayerChange: (layer: Layer) => void;
}

function clampPosition(value: number): number {
  return Math.max(-PANEL_SIZE, Math.min(PANEL_SIZE * 2, Math.round(value)));
}

function clampSize(value: number): number {
  return Math.max(MIN_SIZE, Math.min(MAX_SIZE, Math.round(value)));
}

export default function Stage({ panel, preview, selectedLayerId, onSelect, onLayerChange }: Props) {
  const selected = panel.layers.find((layer) => layer.id === selectedLayerId) ?? null;

  const startMove = (event: ReactPointerEvent<HTMLDivElement>, layer: Layer) => {
    event.preventDefault();
    event.stopPropagation();
    onSelect(layer.id);
    const origin = { x: event.clientX, y: event.clientY, layerX: layer.x, layerY: layer.y };

    const move = (moveEvent: PointerEvent) => {
      const dx = Math.round((moveEvent.clientX - origin.x) / SCALE);
      const dy = Math.round((moveEvent.clientY - origin.y) / SCALE);
      onLayerChange({
        ...layer,
        x: clampPosition(origin.layerX + dx),
        y: clampPosition(origin.layerY + dy),
      });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  const startResize = (
    event: ReactPointerEvent<HTMLSpanElement>,
    layer: Layer,
    corner: Corner,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    onSelect(layer.id);
    const origin = {
      x: event.clientX,
      y: event.clientY,
      left: layer.x,
      top: layer.y,
      width: layer.w,
      height: layer.h,
    };

    const move = (moveEvent: PointerEvent) => {
      const dx = Math.round((moveEvent.clientX - origin.x) / SCALE);
      const dy = Math.round((moveEvent.clientY - origin.y) / SCALE);

      let left = origin.left;
      let top = origin.top;
      let width = origin.width;
      let height = origin.height;

      if (corner.includes("e")) width = clampSize(origin.width + dx);
      if (corner.includes("s")) height = clampSize(origin.height + dy);
      if (corner.includes("w")) {
        width = clampSize(origin.width - dx);
        left = origin.left + (origin.width - width);
      }
      if (corner.includes("n")) {
        height = clampSize(origin.height - dy);
        top = origin.top + (origin.height - height);
      }

      onLayerChange({ ...layer, x: left, y: top, w: width, h: height });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div className="canvas-area">
      <div
        className="canvas"
        style={{ width: PANEL_SIZE * SCALE, height: PANEL_SIZE * SCALE }}
        onPointerDown={() => onSelect(null)}
      >
        {preview ? (
          <img className="canvas-image" src={preview} alt="Panel preview" draggable={false} />
        ) : (
          <div className="canvas-placeholder">Waiting for the preview…</div>
        )}

        {panel.layers.map((layer) => {
          const isSelected = layer.id === selectedLayerId;
          return (
            <div
              key={layer.id}
              className={`layer-box ${isSelected ? "is-selected" : ""} ${layer.visible ? "" : "is-hidden"}`}
              style={{
                left: layer.x * SCALE,
                top: layer.y * SCALE,
                width: layer.w * SCALE,
                height: layer.h * SCALE,
              }}
              onPointerDown={(event) => startMove(event, layer)}
            >
              <span className="layer-tag">
                {layer.kind === "metric" ? layer.metric : layer.source}
              </span>

              {isSelected &&
                CORNERS.map((corner) => (
                  <span
                    key={corner.dir}
                    className={`resize-handle handle-${corner.dir}`}
                    style={{ ...corner.style, cursor: corner.cursor }}
                    onPointerDown={(event) => startResize(event, layer, corner.dir)}
                  />
                ))}
            </div>
          );
        })}
      </div>

      <div className="canvas-caption">
        <span>128 × 128 pixels</span>
        <span>
          {selected
            ? `x ${selected.x}, y ${selected.y} · ${selected.w} × ${selected.h}${
                (selected.kind === "text" || selected.widget === "number") && !selected.auto_scale
                  ? " · fixed text size"
                  : ""
              }`
            : "Drag to move · drag a corner to resize"}
        </span>
      </div>
    </div>
  );
}
