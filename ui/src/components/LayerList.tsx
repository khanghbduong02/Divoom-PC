import type { Layer } from "../types";
import { metricMeta } from "../types";
import { ChevronIcon, EyeIcon, TrashIcon } from "./icons";

interface Props {
  layers: Layer[];
  selectedId: string | null;
  onSelect: (layerId: string) => void;
  onToggle: (layer: Layer) => void;
  onDelete: (layerId: string) => void;
  onMove: (layerId: string, direction: -1 | 1) => void;
  onAddMetric: () => void;
  onAddText: () => void;
}

function label(layer: Layer): string {
  if (layer.kind === "text") {
    if (layer.source === "clock") return "Clock";
    if (layer.source === "date") return "Date";
    return layer.text || "Text";
  }
  const meta = metricMeta(layer.metric);
  return layer.widget === "bar" ? `${meta.label} bar` : meta.label;
}

function detail(layer: Layer): string {
  if (layer.kind === "text") {
    return layer.source === "static" ? `At ${layer.x}, ${layer.y}` : "Automatic";
  }
  return `${layer.w} × ${layer.h} pixels`;
}

export default function LayerList({
  layers,
  selectedId,
  onSelect,
  onToggle,
  onDelete,
  onMove,
  onAddMetric,
  onAddText,
}: Props) {
  return (
    <section className="layer-section">
      <div className="section-header">
        <h2 className="section-title">Layers</h2>
        <span className="layer-count">{layers.length}</span>
      </div>

      <div className="add-buttons">
        <button type="button" className="button-small" onClick={onAddMetric}>
          Add metric
        </button>
        <button type="button" className="button-small" onClick={onAddText}>
          Add text
        </button>
      </div>

      {layers.length === 0 ? (
        <p className="empty-hint">
          This panel has no layers yet. Add a metric to show a sensor reading.
        </p>
      ) : (
        <ul className="layer-items">
          {layers.map((layer, index) => (
            <li key={layer.id} className={layer.id === selectedId ? "is-selected" : ""}>
              <button type="button" className="layer-main" onClick={() => onSelect(layer.id)}>
                <span className="layer-name">{label(layer)}</span>
                <span className="layer-detail">{detail(layer)}</span>
              </button>
              <div className="layer-tools">
                <button
                  type="button"
                  className={`icon-button ${layer.visible ? "" : "is-off"}`}
                  title={layer.visible ? "Hide layer" : "Show layer"}
                  aria-label={layer.visible ? "Hide layer" : "Show layer"}
                  onClick={() => onToggle(layer)}
                >
                  <EyeIcon off={!layer.visible} />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  title="Move up"
                  aria-label="Move up"
                  disabled={index === 0}
                  onClick={() => onMove(layer.id, -1)}
                >
                  <ChevronIcon up />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  title="Move down"
                  aria-label="Move down"
                  disabled={index === layers.length - 1}
                  onClick={() => onMove(layer.id, 1)}
                >
                  <ChevronIcon />
                </button>
                <button
                  type="button"
                  className="icon-button"
                  title="Delete layer"
                  aria-label="Delete layer"
                  onClick={() => onDelete(layer.id)}
                >
                  <TrashIcon />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
