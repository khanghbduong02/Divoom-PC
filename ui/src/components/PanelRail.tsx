import { useRef, useState } from "react";
import type { Panel } from "../types";
import { GripIcon } from "./icons";

interface Props {
  panels: Panel[];
  previews: string[];
  selected: number;
  onSelect: (index: number) => void;
  onReorder: (from: number, to: number) => void;
}

export default function PanelRail({ panels, previews, selected, onSelect, onReorder }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>, index: number) => {
    event.preventDefault();
    event.stopPropagation();

    let target = index;
    let moved = false;
    setDragging(index);
    setDropTarget(index);

    const hitTest = (clientX: number, clientY: number): number => {
      const items = Array.from(listRef.current?.querySelectorAll<HTMLElement>(".panel-item") ?? []);
      return items.findIndex((item) => {
        const rect = item.getBoundingClientRect();
        return (
          clientX >= rect.left &&
          clientX <= rect.right &&
          clientY >= rect.top &&
          clientY <= rect.bottom
        );
      });
    };

    const move = (moveEvent: PointerEvent) => {
      const hit = hitTest(moveEvent.clientX, moveEvent.clientY);
      if (hit >= 0) {
        target = hit;
        moved = true;
        setDropTarget(hit);
      }
    };

    const finish = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      setDragging(null);
      setDropTarget(null);
      if (moved && target !== index) {
        onReorder(index, target);
      }
    };

    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
  };

  return (
    <section className="panel-list">
      <h2 className="section-title">Panels</h2>
      <div className="panel-items" ref={listRef}>
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
          >
            <button
              type="button"
              className="panel-grip"
              title="Drag to reorder"
              aria-label={`Reorder panel ${index + 1}`}
              onPointerDown={(event) => startDrag(event, index)}
            >
              <GripIcon />
            </button>

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
      <p className="panel-hint">Drag the dots to reorder panels.</p>
    </section>
  );
}
