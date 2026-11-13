import type { Panel } from "../types";

interface Props {
  panels: Panel[];
  previews: string[];
  selected: number;
  onSelect: (index: number) => void;
}

export default function PanelRail({ panels, previews, selected, onSelect }: Props) {
  return (
    <nav className="panel-rail" aria-label="Panels">
      {panels.map((panel, index) => (
        <button
          key={index}
          type="button"
          className={`panel-tab ${index === selected ? "is-active" : ""}`}
          onClick={() => onSelect(index)}
          title={`Panel ${index + 1} · ${panel.layers.length} layer(s)`}
        >
          <span className="panel-thumb">
            {previews[index] ? (
              <img src={previews[index]} alt="" />
            ) : (
              <span className="panel-thumb-empty" />
            )}
          </span>
          <span className="panel-index">{index + 1}</span>
        </button>
      ))}
    </nav>
  );
}
