import type { PointerEvent as ReactPointerEvent } from "react";
import type { Layer, Panel } from "../types";
import { PANEL_SIZE } from "../types";

const SCALE = 4;

interface Props {
  panel: Panel;
  preview: string | undefined;
  selectedLayerId: string | null;
  onSelect: (layerId: string | null) => void;
  onLayerChange: (layer: Layer) => void;
}

function clamp(value: number): number {
  return Math.max(-PANEL_SIZE, Math.min(PANEL_SIZE * 2, Math.round(value)));
}

export default function Stage({ panel, preview, selectedLayerId, onSelect, onLayerChange }: Props) {
  const startDrag = (event: ReactPointerEvent<HTMLDivElement>, layer: Layer) => {
    event.preventDefault();
    event.stopPropagation();
    onSelect(layer.id);
    const origin = { x: event.clientX, y: event.clientY, layerX: layer.x, layerY: layer.y };

    const move = (moveEvent: PointerEvent) => {
      const dx = Math.round((moveEvent.clientX - origin.x) / SCALE);
      const dy = Math.round((moveEvent.clientY - origin.y) / SCALE);
      onLayerChange({ ...layer, x: clamp(origin.layerX + dx), y: clamp(origin.layerY + dy) });
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };

  return (
    <div className="stage-wrap">
      <div
        className="stage"
        style={{ width: PANEL_SIZE * SCALE, height: PANEL_SIZE * SCALE }}
        onPointerDown={() => onSelect(null)}
      >
        {preview ? (
          <img className="stage-image" src={preview} alt="Panel preview" draggable={false} />
        ) : (
          <div className="stage-empty">waiting for preview…</div>
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
              onPointerDown={(event) => startDrag(event, layer)}
            >
              <span className="layer-tag">
                {layer.kind === "metric" ? layer.metric : layer.source}
              </span>
            </div>
          );
        })}
      </div>
      <p className="stage-hint">
        128 × 128 device pixels · drag a box to move it (snaps to whole pixels)
      </p>
    </div>
  );
}
