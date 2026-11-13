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
import { METRICS, metricMeta } from "./types";
import Toolbar from "./components/Toolbar";
import PanelRail from "./components/PanelRail";
import Stage from "./components/Stage";
import LayerList from "./components/LayerList";
import Inspector from "./components/Inspector";
import DeviceWizard from "./components/DeviceWizard";
import Diagnostics from "./components/Diagnostics";

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
    text: "",
    source: "static",
    x: 6,
    y: Math.min(88, 8 + stacked * 22),
    w: 116,
    h: 40,
    color: "#FFFFFF",
    track_color: "#2A2A2A",
    scale: 3,
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
    text: "LABEL",
    source: "static",
    x: 6,
    y: Math.min(104, 8 + stacked * 22),
    w: 116,
    h: 14,
    color: "#FFFFFF",
    track_color: "#2A2A2A",
    scale: 2,
    decimals: 0,
    unit: "",
    min_value: 0,
    max_value: 100,
    align: "left",
    visible: true,
  };
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
  const [wire, setWire] = useState<WireStatus>("connecting");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const skipFirstSave = useRef(true);

  const loadConfig = useCallback(async () => {
    const config = await api.getConfig();
    setDevice(config.device);
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
          setBootError(
            error instanceof Error ? error.message : "Could not reach the local agent.",
          );
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
          // ignore a malformed tick; the next one arrives in a moment
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

  // save the theme when the editor stops moving
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

  // push the draft to the preview renderer while dragging
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

  const updatePanel = useCallback(
    (index: number, updater: (current: Panel) => Panel) => {
      setTheme((current) => {
        if (!current) return current;
        return {
          ...current,
          panels: current.panels.map((existing, position) =>
            position === index ? updater(existing) : existing,
          ),
        };
      });
    },
    [],
  );

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
    updatePanel(selectedPanel, (current) => ({
      ...current,
      layers: [...current.layers, layer],
    }));
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

  const applyPreset = async (presetId: string) => {
    if (!presetId) return;
    try {
      const reply = await api.applyPreset(presetId);
      setTheme(reply.theme);
      setSelectedLayerId(null);
      setNotice({ tone: "info", text: `Loaded ${reply.theme.name}. Press Send to put it on the panels.` });
    } catch (error) {
      setNotice(noticeFrom(error));
    }
  };

  const send = async () => {
    setSending(true);
    setNotice(null);
    try {
      const reply = await api.send();
      const bytes = reply.results.reduce((sum, result) => sum + result.bytes, 0);
      setNotice({
        tone: "ok",
        text: `Sent ${reply.results.length} panel(s), ${bytes} bytes total.`,
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
      setNotice({ tone: "info", text: "Background image added." });
    } catch (error) {
      setNotice(noticeFrom(error));
    } finally {
      setUploading(false);
    }
  };

  if (bootError) {
    return (
      <div className="boot boot-error">
        <h1>Cannot reach the agent</h1>
        <p>{bootError}</p>
        <p className="help">
          Open the URL the agent printed, including its <code>?token=</code> part, then reload.
        </p>
      </div>
    );
  }

  if (!theme || !panel) {
    return <div className="boot">Loading editor…</div>;
  }

  return (
    <div className="app">
      <Toolbar
        theme={theme}
        presets={presets}
        device={device}
        wire={wire}
        sending={sending}
        saveState={saveState}
        onPreset={(id) => void applyPreset(id)}
        onSend={() => void send()}
        onWizard={() => setWizardOpen(true)}
        onDiagnostics={() => setDiagnosticsOpen(true)}
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
          />
          <LayerList
            layers={panel.layers}
            selectedId={selectedLayerId}
            onSelect={setSelectedLayerId}
            onToggle={(layer) => updateLayer(layer.id, { visible: !layer.visible })}
            onDelete={deleteLayer}
            onMove={moveLayer}
            onAddMetric={() => addLayer(makeMetricLayer("cpu_percent", panel.layers.length))}
            onAddText={() => addLayer(makeTextLayer(panel.layers.length))}
          />
        </aside>

        <main className="center">
          <Stage
            panel={panel}
            preview={previews[selectedPanel]}
            selectedLayerId={selectedLayerId}
            onSelect={setSelectedLayerId}
            onLayerChange={(layer) => updateLayer(layer.id, { x: layer.x, y: layer.y })}
          />

          <div className="sensor-strip">
            {METRICS.map((metric) => {
              const value = sensors[metric.key];
              return (
                <span key={metric.key} className={value === null || value === undefined ? "is-missing" : ""}>
                  <em>{metric.label}</em>
                  {value === null || value === undefined
                    ? "--"
                    : `${Number(value).toFixed(metric.decimals)}${metric.unit}`}
                </span>
              );
            })}
          </div>

          {notice && (
            <div className={`notice notice-${notice.tone}`}>
              <strong>{notice.text}</strong>
              {notice.hint && <p>{notice.hint}</p>}
              {notice.raw && <pre className="raw">{notice.raw}</pre>}
            </div>
          )}
        </main>

        <aside className="rightbar">
          <Inspector
            panel={panel}
            layer={selectedLayer}
            uploading={uploading}
            onLayer={(patch) => selectedLayer && updateLayer(selectedLayer.id, patch)}
            onPanel={(patch) => updatePanel(selectedPanel, (current) => ({ ...current, ...patch }))}
            onBackground={(patch) =>
              updatePanel(selectedPanel, (current) => ({
                ...current,
                background: { ...current.background, ...patch },
              }))
            }
            onUpload={(file) => void upload(file)}
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
    </div>
  );
}
