import type { Panel } from "../types";

interface Props {
  panels: Panel[];
  previews: string[];
  selected: number;
  onSelect: (index: number) => void;
}

export default function PanelRail({ panels, previews, selected, onSelect }: Props) {
  return (
    <section className="panel-list">
      <h2 className="section-title">Panels</h2>
      <div className="panel-items">
        {panels.map((panel, index) => (
          <button
            key={index}
            type="button"
            className={`panel-item ${index === selected ? "is-selected" : ""}`}
            onClick={() => onSelect(index)}
          >
            <span className="panel-frame">
              {previews[index] ? (
                <img src={previews[index]} alt="" />
              ) : (
                <span className="panel-frame-empty" />
              )}
            </span>
            <span className="panel-caption">
              Panel {index + 1}
              <em>
                {panel.layers.length} {panel.layers.length === 1 ? "layer" : "layers"}
              </em>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
