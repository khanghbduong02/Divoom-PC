import { useState } from "react";
import type { ReactNode } from "react";
import type { Align, Layer, MetricKey, Panel, PresetMeta, Widget } from "../types";
import { METRICS, metricMeta } from "../types";
import { mediaUrl } from "../api";

interface Props {
  panel: Panel;
  layer: Layer | null;
  presets: PresetMeta[];
  uploading: boolean;
  onLayer: (patch: Partial<Layer>) => void;
  onPanel: (patch: Partial<Panel>) => void;
  onBackground: (patch: Partial<Panel["background"]>) => void;
  onUpload: (file: File) => void;
  onApplyPanelPreset: (presetId: string) => void;
  onClearLayers: () => void;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
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
  presets,
  uploading,
  onLayer,
  onPanel,
  onBackground,
  onUpload,
  onApplyPanelPreset,
  onClearLayers,
}: Props) {
  const [themeChoice, setThemeChoice] = useState("");
  const background = panel.background;

  return (
    <div className="inspector">
      <section className="field-group">
        <h2 className="section-title">Panel appearance</h2>

        <Field label="Background">
          <select
            value={background.kind}
            onChange={(event) =>
              onBackground({ kind: event.target.value as Panel["background"]["kind"] })
            }
          >
            <option value="color">Solid colour</option>
            <option value="image">Picture</option>
          </select>
        </Field>

        <Field label="Colour">
          <span className="color-field">
            <input
              type="color"
              value={background.color}
              onChange={(event) => onBackground({ color: event.target.value.toUpperCase() })}
            />
            <code>{background.color}</code>
          </span>
        </Field>

        {background.kind === "image" && (
          <>
            <Field label="Fit">
              <select
                value={background.fit}
                onChange={(event) =>
                  onBackground({ fit: event.target.value as Panel["background"]["fit"] })
                }
              >
                <option value="crop">Fill the panel</option>
                <option value="fit">Fit inside</option>
                <option value="stretch">Stretch</option>
              </select>
            </Field>
            <Field label="Darken">
              <NumberInput
                value={background.dim}
                min={0}
                max={100}
                onChange={(dim) => onBackground({ dim })}
              />
            </Field>
            <div className="picture-row">
              {background.image ? (
                <img className="picture-thumb" src={mediaUrl(background.image)} alt="" />
              ) : (
                <span className="picture-thumb picture-empty">None</span>
              )}
              <div className="picture-actions">
                <label className="file-button">
                  {uploading ? "Uploading…" : "Choose picture"}
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
                  <button type="button" className="button-small" onClick={() => onBackground({ image: null })}>
                    Remove
                  </button>
                )}
              </div>
            </div>
          </>
        )}

        <Field label="Accent">
          <span className="color-field">
            <input
              type="color"
              value={panel.accent}
              onChange={(event) => onPanel({ accent: event.target.value.toUpperCase() })}
            />
            <code>{panel.accent}</code>
          </span>
        </Field>

        <div className="subgroup">
          <span className="subgroup-title">Theme for this panel only</span>
          <div className="theme-row">
            <select value={themeChoice} onChange={(event) => setThemeChoice(event.target.value)}>
              <option value="">Choose a theme…</option>
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="button-small"
              disabled={!themeChoice}
              onClick={() => onApplyPanelPreset(themeChoice)}
            >
              Apply
            </button>
          </div>
          <p className="hint">Replaces this panel's layers and background. Other panels stay as they are.</p>
        </div>

        <button
          type="button"
          className="button-small danger-ghost"
          disabled={panel.layers.length === 0}
          onClick={onClearLayers}
        >
          Remove all layers from this panel
        </button>
      </section>

      {layer ? (
        <section className="field-group">
          <h2 className="section-title">{layer.kind === "metric" ? "Sensor layer" : "Text layer"}</h2>

          {layer.kind === "metric" ? (
            <>
              <Field label="Shows">
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
              </Field>
              <Field label="Style">
                <select
                  value={layer.widget}
                  onChange={(event) => onLayer({ widget: event.target.value as Widget })}
                >
                  <option value="number">Large number</option>
                  <option value="bar">Progress bar</option>
                </select>
              </Field>
            </>
          ) : (
            <>
              <Field label="Shows">
                <select
                  value={layer.source}
                  onChange={(event) => onLayer({ source: event.target.value as Layer["source"] })}
                >
                  <option value="static">Fixed text</option>
                  <option value="clock">Time</option>
                  <option value="date">Date</option>
                </select>
              </Field>
              {layer.source === "static" && (
                <Field label="Text">
                  <input
                    type="text"
                    value={layer.text}
                    onChange={(event) => onLayer({ text: event.target.value })}
                  />
                </Field>
              )}
            </>
          )}

          <div className="field-grid">
            <Field label="Left">
              <NumberInput value={layer.x} onChange={(x) => onLayer({ x })} />
            </Field>
            <Field label="Top">
              <NumberInput value={layer.y} onChange={(y) => onLayer({ y })} />
            </Field>
            <Field label="Width">
              <NumberInput value={layer.w} min={1} onChange={(w) => onLayer({ w })} />
            </Field>
            <Field label="Height">
              <NumberInput value={layer.h} min={1} onChange={(h) => onLayer({ h })} />
            </Field>
          </div>

          <Field label="Align">
            <select
              value={layer.align}
              onChange={(event) => onLayer({ align: event.target.value as Align })}
            >
              <option value="left">Left</option>
              <option value="center">Centre</option>
              <option value="right">Right</option>
            </select>
          </Field>

          <Field label="Colour">
            <span className="color-field">
              <input
                type="color"
                value={layer.color}
                onChange={(event) => onLayer({ color: event.target.value.toUpperCase() })}
              />
              <code>{layer.color}</code>
            </span>
          </Field>

          {layer.kind === "metric" && layer.widget === "bar" && (
            <Field label="Bar track">
              <span className="color-field">
                <input
                  type="color"
                  value={layer.track_color}
                  onChange={(event) => onLayer({ track_color: event.target.value.toUpperCase() })}
                />
                <code>{layer.track_color}</code>
              </span>
            </Field>
          )}

          {(layer.kind === "text" || layer.widget === "number") && (
            <>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layer.auto_scale}
                  onChange={(event) => onLayer({ auto_scale: event.target.checked })}
                />
                <span>Scale text to fit the box</span>
              </label>
              <p className="hint">
                {layer.auto_scale
                  ? "Drag the corner handles on the panel to make the text bigger or smaller."
                  : "Text keeps its size. Tick the box above to resize it by dragging."}
              </p>
            </>
          )}

          <div className="field-grid">
            {!layer.auto_scale && (
              <Field label="Text size">
                <NumberInput
                  value={layer.scale}
                  min={1}
                  max={8}
                  onChange={(scale) => onLayer({ scale })}
                />
              </Field>
            )}
            <Field label="Decimals">
              <NumberInput
                value={layer.decimals}
                min={0}
                max={3}
                onChange={(decimals) => onLayer({ decimals })}
              />
            </Field>
            <Field label="Unit">
              <input
                type="text"
                value={layer.unit}
                onChange={(event) => onLayer({ unit: event.target.value })}
              />
            </Field>
            {layer.kind === "metric" && (
              <>
                <Field label="Minimum">
                  <NumberInput value={layer.min_value} onChange={(min_value) => onLayer({ min_value })} />
                </Field>
                <Field label="Maximum">
                  <NumberInput value={layer.max_value} onChange={(max_value) => onLayer({ max_value })} />
                </Field>
              </>
            )}
          </div>
        </section>
      ) : (
        <p className="empty-hint">
          Select a layer on the panel or in the list to change its contents.
        </p>
      )}
    </div>
  );
}
