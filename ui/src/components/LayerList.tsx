import type { Layer } from "../types";
import { metricMeta } from "../types";

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
  return `${meta.label} · ${layer.widget}`;
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
    <section className="layer-list">
      <header>
        <h2>Layers</h2>
        <span className="count">{layers.length}</span>
      </header>

      <div className="layer-add">
        <button type="button" onClick={onAddMetric}>
          + Metric
        </button>
        <button type="button" onClick={onAddText}>
          + Text
        </button>
      </div>

      {layers.length === 0 && <p className="empty">No layers yet. Add a metric or a label.</p>}

      <ul>
        {layers.map((layer, index) => (
          <li key={layer.id} className={layer.id === selectedId ? "is-active" : ""}>
            <button type="button" className="layer-name" onClick={() => onSelect(layer.id)}>
              {label(layer)}
            </button>
            <div className="layer-actions">
              <button
                type="button"
                title={layer.visible ? "Hide layer" : "Show layer"}
                onClick={() => onToggle(layer)}
              >
                {layer.visible ? "◉" : "○"}
              </button>
              <button
                type="button"
                title="Move up"
                disabled={index === 0}
                onClick={() => onMove(layer.id, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                title="Move down"
                disabled={index === layers.length - 1}
                onClick={() => onMove(layer.id, 1)}
              >
                ↓
              </button>
              <button type="button" title="Delete layer" onClick={() => onDelete(layer.id)}>
                ×
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
