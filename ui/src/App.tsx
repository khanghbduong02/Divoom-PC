import { useCallback, useEffect, useRef, useState } from "react";
import { ApiFailure, api, wsUrl } from "./api";
import type {
  DeviceSummary,
  Layer,
  MetricKey,
  Panel,
  PresetMeta,
  SensorValues,
  Theme,
  WireStatus,
} from "./types";
import { METRICS, PANEL_SIZE, metricMeta } from "./types";
import Toolbar from "./components/Toolbar";
import PanelRail from "./components/PanelRail";
import Stage from "./components/Stage";
import LayerList from "./components/LayerList";
import Inspector from "./components/Inspector";
import DeviceWizard from "./components/DeviceWizard";
import Diagnostics from "./components/Diagnostics";
import Settings from "./components/Settings";
import Help from "./components/Help";

type SaveState = "idle" | "saving" | "saved" | "error";

interface Notice {
  tone: "ok" | "error" | "info";
  text: string;
  hint?: string | null;
  raw?: string | null;
}

function newId(): string {
  return Math.random().toString(16).slice(2, 10);
}

function makeMetricLayer(metric: MetricKey, stacked: number): Layer {
  const meta = metricMeta(metric);
  return {
    id: newId(),
    kind: "metric",
    metric,
    widget: "number",
    history_minutes: 10,
    text: "",
    source: "static",
    x: 6,
    y: Math.min(88, 8 + stacked * 22),
    w: 116,
    h: 40,
    color: "#FFFFFF",
    track_color: "#2A2A2A",
    scale: 8,
    auto_scale: true,
    decimals: meta.decimals,
    unit: meta.unit,
    min_value: meta.min,
    max_value: meta.max,
    align: "center",
    visible: true,
  };
}

function makeTextLayer(stacked: number): Layer {
  return {
    id: newId(),
    kind: "text",
    metric: "cpu_percent",
    widget: "number",
    history_minutes: 10,
    text: "LABEL",
    source: "static",
    x: 6,
    y: Math.min(104, 8 + stacked * 22),
    w: 116,
    h: 14,
    color: "#FFFFFF",
    track_color: "#2A2A2A",
    scale: 8,
    auto_scale: true,
    decimals: 0,
    unit: "",
    min_value: 0,
    max_value: 100,
    align: "left",
    visible: true,
  };
}

const RECENT_COLORS_KEY = "gate-studio.recent-colors";

function loadRecentColors(): string[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(RECENT_COLORS_KEY) ?? "[]");
    if (Array.isArray(stored)) {
      return stored
        .filter((color): color is string => typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color))
        .slice(0, 8);
    }
  } catch {
    // private mode or a corrupt value: start empty
  }
  return [];
}

function noticeFrom(error: unknown): Notice {
  if (error instanceof ApiFailure) {
    return { tone: "error", text: error.message, hint: error.hint, raw: error.raw };
  }
  return { tone: "error", text: error instanceof Error ? error.message : String(error) };
}

export default function App() {
  const [theme, setTheme] = useState<Theme | null>(null);
  const [presets, setPresets] = useState<PresetMeta[]>([]);
  const [device, setDevice] = useState<DeviceSummary | null>(null);
  const [previews, setPreviews] = useState<string[]>([]);
  const [sensors, setSensors] = useState<SensorValues>({});
  const [selectedPanel, setSelectedPanel] = useState(0);
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);
  const [applyingPanel, setApplyingPanel] = useState(false);
  const [recentColors, setRecentColors] = useState<string[]>(loadRecentColors);
  const [wire, setWire] = useState<WireStatus>("connecting");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [stageScale, setStageScale] = useState(4);
  const [temperatureUnit, setTemperatureUnit] = useState<"c" | "f">("c");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const skipFirstSave = useRef(true);
  const editorRef = useRef<HTMLElement | null>(null);

  // the tray menu can deep-link to settings
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("settings")) {
      setSettingsOpen(true);
      url.searchParams.delete("settings");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  // scale the 128px canvas to whatever room the middle column has;
  // re-run once the editor replaces the loading screen
  const hasTheme = theme !== null;
  useEffect(() => {
    if (!hasTheme) return;
    const element = editorRef.current;
    if (!element) return;
    const measure = () => {
      const padding = 40;
      const available = element.clientWidth - padding;
      const raw = Math.min(4.5, Math.max(2.25, available / PANEL_SIZE));
      setStageScale(Math.max(2.25, Math.floor(raw * 4) / 4));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [hasTheme]);

  const loadConfig = useCallback(async () => {
    const config = await api.getConfig();
    setDevice(config.device);
    setTemperatureUnit(config.settings.temperature_unit);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [themeReply, presetReply] = await Promise.all([api.getTheme(), api.getPresets()]);
        if (cancelled) return;
        setTheme(themeReply.theme);
        setPresets(presetReply.presets);
        await loadConfig();
      } catch (error) {
        if (!cancelled) {
          setBootError(error instanceof Error ? error.message : "Could not reach the local agent.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadConfig]);

  // live preview socket
  useEffect(() => {
    let closed = false;
    let retry = 0;

    const connect = () => {
      const socket = new WebSocket(wsUrl());
      socketRef.current = socket;
      socket.onopen = () => setWire("live");
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as {
            type: string;
            sensors: SensorValues;
            panels: { index: number; png: string }[];
            device: DeviceSummary;
          };
          if (message.type !== "tick") return;
          setPreviews((current) => {
            const next = [...current];
            for (const panel of message.panels) {
              next[panel.index] = `data:image/png;base64,${panel.png}`;
            }
            return next;
          });
          setSensors(message.sensors);
          setDevice(message.device);
        } catch {
          // a malformed tick is not worth surfacing; the next one arrives shortly
        }
      };
      socket.onclose = () => {
        setWire("offline");
        if (!closed) {
          retry = window.setTimeout(connect, 2000);
        }
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retry);
      socketRef.current?.close();
    };
  }, []);

  // save after the editor settles
  useEffect(() => {
    if (!theme) return;
    if (skipFirstSave.current) {
      skipFirstSave.current = false;
      return;
    }
    setSaveState("saving");
    const timer = window.setTimeout(() => {
      api
        .putTheme(theme)
        .then(() => setSaveState("saved"))
        .catch((error) => {
          setSaveState("error");
          setNotice(noticeFrom(error));
        });
    }, 450);
    return () => window.clearTimeout(timer);
  }, [theme]);

  // stream drafts to the preview renderer
  useEffect(() => {
    if (!theme) return;
    const timer = window.setTimeout(() => {
      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "theme", theme }));
      }
    }, 120);
    return () => window.clearTimeout(timer);
  }, [theme]);

  const panel: Panel | null = theme ? theme.panels[selectedPanel] ?? theme.panels[0] : null;
  const selectedLayer = panel?.layers.find((layer) => layer.id === selectedLayerId) ?? null;

  const updatePanel = useCallback((index: number, updater: (current: Panel) => Panel) => {
    setTheme((current) => {
      if (!current) return current;
      return {
        ...current,
        panels: current.panels.map((existing, position) =>
          position === index ? updater(existing) : existing,
        ),
      };
    });
  }, []);

  const updateLayer = useCallback(
    (layerId: string, patch: Partial<Layer>) => {
      updatePanel(selectedPanel, (current) => ({
        ...current,
        layers: current.layers.map((layer) =>
          layer.id === layerId ? { ...layer, ...patch } : layer,
        ),
      }));
    },
    [selectedPanel, updatePanel],
  );

  const addLayer = (layer: Layer) => {
    updatePanel(selectedPanel, (current) => ({ ...current, layers: [...current.layers, layer] }));
    setSelectedLayerId(layer.id);
  };

  const deleteLayer = (layerId: string) => {
    updatePanel(selectedPanel, (current) => ({
      ...current,
      layers: current.layers.filter((layer) => layer.id !== layerId),
    }));
    if (selectedLayerId === layerId) {
      setSelectedLayerId(null);
    }
  };

  const moveLayer = (layerId: string, direction: -1 | 1) => {
    updatePanel(selectedPanel, (current) => {
      const index = current.layers.findIndex((layer) => layer.id === layerId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.layers.length) {
        return current;
      }
      const layers = [...current.layers];
      const [moved] = layers.splice(index, 1);
      layers.splice(target, 0, moved);
      return { ...current, layers };
    });
  };

  const applyPreset = async (presetId: string, panelIndex?: number) => {
    if (!presetId) return;
    try {
      const reply = await api.applyPreset(presetId, panelIndex);
      setTheme(reply.theme);
      setSelectedLayerId(null);
      setNotice({
        tone: "info",
        text:
          panelIndex === undefined
            ? `Loaded “${reply.theme.name}” into the editor for all five panels. Press “Send all” to put it on the Gate.`
            : `Loaded a theme into panel ${panelIndex + 1} in the editor. Press Apply above to send it; other panels are unchanged.`,
      });
    } catch (error) {
      setNotice(noticeFrom(error));
    }
  };

  const movePanel = (from: number, to: number) => {
    if (from === to) return;
    setTheme((current) => {
      if (!current) return current;
      const panels = [...current.panels];
      const [moved] = panels.splice(from, 1);
      panels.splice(to, 0, moved);
      return { ...current, panels };
    });
    setSelectedPanel(to);
    setSelectedLayerId(null);
  };

  const rememberColor = useCallback((color: string) => {
    const normalized = color.toUpperCase();
    setRecentColors((current) => {
      const next = [normalized, ...current.filter((entry) => entry !== normalized)].slice(0, 8);
      try {
        window.localStorage.setItem(RECENT_COLORS_KEY, JSON.stringify(next));
      } catch {
        // not fatal: the palette simply will not survive a reload
      }
      return next;
    });
  }, []);

  const applyPanel = async () => {
    setApplyingPanel(true);
    setNotice(null);
    try {
      const reply = await api.send([selectedPanel]);
      const bytes = reply.results.reduce((sum, result) => sum + result.bytes, 0);
      setNotice({
        tone: "ok",
        text: `Applied panel ${selectedPanel + 1} to the display, ${bytes} bytes.`,
      });
    } catch (error) {
      setNotice(noticeFrom(error));
    } finally {
      setApplyingPanel(false);
    }
  };

  const clearLayers = () => {
    updatePanel(selectedPanel, (current) => ({ ...current, layers: [] }));
    setSelectedLayerId(null);
    setNotice({ tone: "info", text: `Cleared every layer from panel ${selectedPanel + 1}.` });
  };

  const send = async () => {
    setSending(true);
    setNotice(null);
    try {
      const reply = await api.send();
      const bytes = reply.results.reduce((sum, result) => sum + result.bytes, 0);
      setNotice({
        tone: "ok",
        text: `Sent to ${reply.results.length} panel(s), ${bytes} bytes in total.`,
      });
    } catch (error) {
      setNotice(noticeFrom(error));
    } finally {
      setSending(false);
    }
  };

  const upload = async (file: File) => {
    setUploading(true);
    try {
      const reply = await api.uploadMedia(file);
      updatePanel(selectedPanel, (current) => ({
        ...current,
        background: { ...current.background, kind: "image", image: reply.name },
      }));
      setNotice({ tone: "info", text: "Picture added as the panel background." });
    } catch (error) {
      setNotice(noticeFrom(error));
    } finally {
      setUploading(false);
    }
  };

  if (bootError) {
    return (
      <div className="boot">
        <div className="boot-card">
          <h1>Can't reach the editor</h1>
          <p>{bootError}</p>
          <p className="hint">
            Open the link the agent printed, including the <code>?token=</code> part, then
            reload this page.
          </p>
        </div>
      </div>
    );
  }

  if (!theme || !panel) {
    return <div className="boot">Loading…</div>;
  }

  return (
    <div className="app">
      <Toolbar
        presets={presets}
        device={device}
        wire={wire}
        sending={sending}
        saveState={saveState}
        onPreset={(id) => void applyPreset(id)}
        onSend={() => void send()}
        onWizard={() => setWizardOpen(true)}
        onDiagnostics={() => setDiagnosticsOpen(true)}
        onSettings={() => setSettingsOpen(true)}
        onHelp={() => setHelpOpen(true)}
      />

      <div className="workspace">
        <aside className="sidebar">
          <PanelRail
            panels={theme.panels}
            previews={previews}
            selected={selectedPanel}
            onSelect={(index) => {
              setSelectedPanel(index);
              setSelectedLayerId(null);
            }}
            onReorder={movePanel}
          />
          <LayerList
            layers={panel.layers}
            selectedId={selectedLayerId}
            onSelect={setSelectedLayerId}
            onToggle={(layer) => updateLayer(layer.id, { visible: !layer.visible })}
            onDelete={deleteLayer}
            onMove={moveLayer}
            onAddMetric={(metric) => addLayer(makeMetricLayer(metric, panel.layers.length))}
            onAddText={() => addLayer(makeTextLayer(panel.layers.length))}
          />
        </aside>

        <main className="editor" ref={editorRef}>
          <Stage
            panel={panel}
            preview={previews[selectedPanel]}
            selectedLayerId={selectedLayerId}
            scale={stageScale}
            onSelect={setSelectedLayerId}
            onLayerChange={(layer) =>
              updateLayer(layer.id, { x: layer.x, y: layer.y, w: layer.w, h: layer.h })
            }
          />

          {panel.layers.length === 0 && (
            <section className="empty-state">
              <h2>Panel {selectedPanel + 1} is empty</h2>
              <p className="hint">
                Add a sensor reading, or apply a ready-made theme to all five panels.
              </p>
              <div className="empty-actions">
                <button
                  type="button"
                  className="button-small"
                  onClick={() => addLayer(makeMetricLayer("cpu_percent", 0))}
                >
                  Add a CPU readout
                </button>
              </div>
              <div className="preset-cards">
                {presets.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    className="preset-card"
                    onClick={() => void applyPreset(preset.id)}
                  >
                    <strong>{preset.name}</strong>
                    <span>{preset.description}</span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="sensor-row">
            {METRICS.map((metric) => {
              const value = sensors[metric.key];
              const missing = value === null || value === undefined;
              return (
                <span key={metric.key} className={missing ? "sensor is-missing" : "sensor"}>
                  <em>{metric.label}</em>
                  {missing ? "—" : `${Number(value).toFixed(metric.decimals)}${metric.unit}`}
                </span>
              );
            })}
          </div>

          {notice && (
            <div className={`notice notice-${notice.tone}`}>
              <strong>{notice.text}</strong>
              {notice.hint && <p>{notice.hint}</p>}
              {notice.raw && (
                <details className="raw-details">
                  <summary>Show details</summary>
                  <pre>{notice.raw}</pre>
                </details>
              )}
            </div>
          )}
        </main>

        <aside className="properties">
          <Inspector
            panel={panel}
            panelIndex={selectedPanel}
            layer={selectedLayer}
            presets={presets}
            uploading={uploading}
            applying={applyingPanel}
            temperatureUnit={temperatureUnit}
            recentColors={recentColors}
            onColorUsed={rememberColor}
            onApplyPanel={() => void applyPanel()}
            onLayer={(patch) => selectedLayer && updateLayer(selectedLayer.id, patch)}
            onPanel={(patch) => updatePanel(selectedPanel, (current) => ({ ...current, ...patch }))}
            onBackground={(patch) =>
              updatePanel(selectedPanel, (current) => ({
                ...current,
                background: { ...current.background, ...patch },
              }))
            }
            onUpload={(file) => void upload(file)}
            onApplyPanelPreset={(presetId) => void applyPreset(presetId, selectedPanel)}
            onClearLayers={clearLayers}
          />
        </aside>
      </div>

      <DeviceWizard
        open={wizardOpen}
        device={device}
        onClose={() => setWizardOpen(false)}
        onChanged={() => void loadConfig()}
      />
      <Diagnostics open={diagnosticsOpen} onClose={() => setDiagnosticsOpen(false)} />
      <Settings
        open={settingsOpen}
        onClose={() => {
          setSettingsOpen(false);
          void loadConfig();
        }}
      />
      <Help open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
