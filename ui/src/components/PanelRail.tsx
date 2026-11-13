import { useState } from "react";
import type { Panel } from "../types";

interface Props {
  panels: Panel[];
  previews: string[];
  selected: number;
  onSelect: (index: number) => void;
  onReorder: (from: number, to: number) => void;
}

export default function PanelRail({ panels, previews, selected, onSelect, onReorder }: Props) {
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);

  const finishDrag = () => {
    setDragging(null);
    setDropTarget(null);
  };

  return (
    <section className="panel-list">
      <h2 className="section-title">Panels</h2>
      <div className="panel-items">
        {panels.map((panel, index) => (
          <div
            key={index}
            className={[
              "panel-item",
              index === selected ? "is-selected" : "",
              dragging === index ? "is-dragging" : "",
              dropTarget === index && dragging !== null && dragging !== index ? "is-drop-target" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            draggable
            role="button"
            tabIndex={0}
            aria-label={`Panel ${index + 1}, ${panel.layers.length} layers`}
            onClick={() => onSelect(index)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(index);
              }
            }}
            onDragStart={(event) => {
              setDragging(index);
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", String(index));
            }}
            onDragEnd={finishDrag}
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              setDropTarget(index);
            }}
            onDragLeave={() => setDropTarget((current) => (current === index ? null : current))}
            onDrop={(event) => {
              event.preventDefault();
              const from = Number(event.dataTransfer.getData("text/plain"));
              if (!Number.isNaN(from) && from !== index) {
                onReorder(from, index);
              }
              finishDrag();
            }}
          >
            <span className="panel-frame">
              {previews[index] ? (
                <img src={previews[index]} alt="" draggable={false} />
              ) : (
                <span className="panel-frame-empty" />
              )}
            </span>
            <span className="panel-caption">
              Panel {index + 1}
              <em>
                {panel.layers.length === 0
                  ? "empty"
                  : `${panel.layers.length} ${panel.layers.length === 1 ? "layer" : "layers"}`}
              </em>
            </span>
          </div>
        ))}
      </div>
      <p className="panel-hint">Drag a panel onto another to reorder them.</p>
    </section>
  );
}
