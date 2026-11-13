import type { ReactNode } from "react";
import type { Align, Layer, MetricKey, Panel, Widget } from "../types";
import { METRICS, metricMeta } from "../types";
import { mediaUrl } from "../api";

interface Props {
  panel: Panel;
  layer: Layer | null;
  uploading: boolean;
  onLayer: (patch: Partial<Layer>) => void;
  onPanel: (patch: Partial<Panel>) => void;
  onBackground: (patch: Partial<Panel["background"]>) => void;
  onUpload: (file: File) => void;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="row">
      <span>{label}</span>
      {children}
    </label>
  );
}

function NumberInput({
  value,
  min,
  max,
  step,
  onChange,
}: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(event) => onChange(Number(event.target.value))}
    />
  );
}

export default function Inspector({
  panel,
  layer,
  uploading,
  onLayer,
  onPanel,
  onBackground,
  onUpload,
}: Props) {
  const background = panel.background;

  return (
    <section className="inspector">
      <header>
        <h2>Panel</h2>
      </header>

      <div className="group">
        <Row label="Background">
          <select
            value={background.kind}
            onChange={(event) => {
              const kind = event.target.value as Panel["background"]["kind"];
              onBackground({ kind });
              if (kind === "image" && !background.image) {
                onBackground({ color: background.color });
              }
            }}
          >
            <option value="color">Colour</option>
            <option value="image">Image</option>
          </select>
        </Row>

        <Row label="Base colour">
          <span className="colour-field">
            <input
              type="color"
              value={background.color}
              onChange={(event) => onBackground({ color: event.target.value.toUpperCase() })}
            />
            <code>{background.color}</code>
          </span>
        </Row>

        {background.kind === "image" && (
          <>
            <Row label="Fit">
              <select
                value={background.fit}
                onChange={(event) =>
                  onBackground({ fit: event.target.value as Panel["background"]["fit"] })
                }
              >
                <option value="crop">Crop to fill</option>
                <option value="fit">Fit (letterbox)</option>
                <option value="stretch">Stretch</option>
              </select>
            </Row>
            <Row label="Dim">
              <NumberInput
                value={background.dim}
                min={0}
                max={100}
                onChange={(dim) => onBackground({ dim })}
              />
            </Row>
            <div className="image-row">
              {background.image ? (
                <img className="image-thumb" src={mediaUrl(background.image)} alt="" />
              ) : (
                <span className="image-thumb image-thumb-empty">none</span>
              )}
              <div className="image-actions">
                <label className="file-button">
                  {uploading ? "Uploading…" : "Choose image"}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
                    disabled={uploading}
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) onUpload(file);
                      event.target.value = "";
                    }}
                  />
                </label>
                {background.image && (
                  <button type="button" onClick={() => onBackground({ image: null })}>
                    Remove
                  </button>
                )}
              </div>
            </div>
          </>
        )}

        <Row label="Accent">
          <span className="colour-field">
            <input
              type="color"
              value={panel.accent}
              onChange={(event) => onPanel({ accent: event.target.value.toUpperCase() })}
            />
            <code>{panel.accent}</code>
          </span>
        </Row>
      </div>

      {layer ? (
        <>
          <header>
            <h2>{layer.kind === "metric" ? "Metric layer" : "Text layer"}</h2>
          </header>
          <div className="group">
            {layer.kind === "metric" ? (
              <>
                <Row label="Metric">
                  <select
                    value={layer.metric}
                    onChange={(event) => {
                      const metric = event.target.value as MetricKey;
                      const meta = metricMeta(metric);
                      onLayer({
                        metric,
                        unit: meta.unit,
                        min_value: meta.min,
                        max_value: meta.max,
                        decimals: meta.decimals,
                      });
                    }}
                  >
                    {METRICS.map((metric) => (
                      <option key={metric.key} value={metric.key}>
                        {metric.label}
                      </option>
                    ))}
                  </select>
                </Row>
                <Row label="Widget">
                  <select
                    value={layer.widget}
                    onChange={(event) => onLayer({ widget: event.target.value as Widget })}
                  >
                    <option value="number">Big number</option>
                    <option value="bar">Bar</option>
                  </select>
                </Row>
              </>
            ) : (
              <>
                <Row label="Source">
                  <select
                    value={layer.source}
                    onChange={(event) =>
                      onLayer({ source: event.target.value as Layer["source"] })
                    }
                  >
                    <option value="static">Static text</option>
                    <option value="clock">Clock (HH:MM)</option>
                    <option value="date">Date</option>
                  </select>
                </Row>
                {layer.source === "static" && (
                  <Row label="Text">
                    <input
                      type="text"
                      value={layer.text}
                      onChange={(event) => onLayer({ text: event.target.value })}
                    />
                  </Row>
                )}
              </>
            )}

            <div className="grid-2">
              <Row label="X">
                <NumberInput value={layer.x} onChange={(x) => onLayer({ x })} />
              </Row>
              <Row label="Y">
                <NumberInput value={layer.y} onChange={(y) => onLayer({ y })} />
              </Row>
              <Row label="Width">
                <NumberInput value={layer.w} min={1} onChange={(w) => onLayer({ w })} />
              </Row>
              <Row label="Height">
                <NumberInput value={layer.h} min={1} onChange={(h) => onLayer({ h })} />
              </Row>
            </div>

            <Row label="Align">
              <select
                value={layer.align}
                onChange={(event) => onLayer({ align: event.target.value as Align })}
              >
                <option value="left">Left</option>
                <option value="center">Centre</option>
                <option value="right">Right</option>
              </select>
            </Row>

            <Row label="Colour">
              <span className="colour-field">
                <input
                  type="color"
                  value={layer.color}
                  onChange={(event) => onLayer({ color: event.target.value.toUpperCase() })}
                />
                <code>{layer.color}</code>
              </span>
            </Row>

            {layer.kind === "metric" && layer.widget === "bar" && (
              <Row label="Track">
                <span className="colour-field">
                  <input
                    type="color"
                    value={layer.track_color}
                    onChange={(event) =>
                      onLayer({ track_color: event.target.value.toUpperCase() })
                    }
                  />
                  <code>{layer.track_color}</code>
                </span>
              </Row>
            )}

            <div className="grid-2">
              <Row label="Text size">
                <NumberInput value={layer.scale} min={1} max={8} onChange={(scale) => onLayer({ scale })} />
              </Row>
              <Row label="Decimals">
                <NumberInput
                  value={layer.decimals}
                  min={0}
                  max={3}
                  onChange={(decimals) => onLayer({ decimals })}
                />
              </Row>
              <Row label="Unit">
                <input
                  type="text"
                  value={layer.unit}
                  onChange={(event) => onLayer({ unit: event.target.value })}
                />
              </Row>
              {layer.kind === "metric" && (
                <>
                  <Row label="Min">
                    <NumberInput value={layer.min_value} onChange={(min_value) => onLayer({ min_value })} />
                  </Row>
                  <Row label="Max">
                    <NumberInput value={layer.max_value} onChange={(max_value) => onLayer({ max_value })} />
                  </Row>
                </>
              )}
            </div>
          </div>
        </>
      ) : (
        <p className="empty">Select a layer on the canvas or in the list to edit it.</p>
      )}
    </section>
  );
}
