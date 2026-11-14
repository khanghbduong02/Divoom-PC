export const PANEL_SIZE = 128;

export type MetricKey =
  | "cpu_percent"
  | "cpu_temp"
  | "gpu_percent"
  | "gpu_temp"
  | "vram_percent"
  | "ram_percent"
  | "disk_percent"
  | "net_up"
  | "net_down"
  | "fan_percent";

export interface MetricMeta {
  key: MetricKey;
  label: string;
  unit: string;
  min: number;
  max: number;
  decimals: number;
}

export const METRICS: MetricMeta[] = [
  { key: "cpu_percent", label: "CPU load", unit: "%", min: 0, max: 100, decimals: 0 },
  { key: "cpu_temp", label: "CPU temp", unit: "°C", min: 20, max: 100, decimals: 0 },
  { key: "gpu_percent", label: "GPU load", unit: "%", min: 0, max: 100, decimals: 0 },
  { key: "gpu_temp", label: "GPU temp", unit: "°C", min: 20, max: 100, decimals: 0 },
  { key: "vram_percent", label: "VRAM", unit: "%", min: 0, max: 100, decimals: 0 },
  { key: "ram_percent", label: "RAM", unit: "%", min: 0, max: 100, decimals: 0 },
  { key: "disk_percent", label: "Disk", unit: "%", min: 0, max: 100, decimals: 0 },
  { key: "net_up", label: "Net up", unit: "MB/s", min: 0, max: 10, decimals: 1 },
  { key: "net_down", label: "Net down", unit: "MB/s", min: 0, max: 10, decimals: 1 },
  { key: "fan_percent", label: "Fan", unit: "%", min: 0, max: 100, decimals: 0 },
];

export function metricMeta(key: MetricKey): MetricMeta {
  return METRICS.find((metric) => metric.key === key) ?? METRICS[0];
}

export type Align = "left" | "center" | "right";
export type Widget = "number" | "bar" | "line";

export function isTemperatureMetric(metric: MetricKey): boolean {
  return metric === "cpu_temp" || metric === "gpu_temp";
}

export interface Layer {
  id: string;
  kind: "metric" | "text";
  metric: MetricKey;
  widget: Widget;
  history_minutes: number;
  text: string;
  source: "static" | "clock" | "date";
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  track_color: string;
  scale: number;
  auto_scale: boolean;
  decimals: number;
  unit: string;
  min_value: number;
  max_value: number;
  align: Align;
  visible: boolean;
}

export interface Background {
  kind: "color" | "image";
  color: string;
  image: string | null;
  fit: "fit" | "crop" | "stretch";
  dim: number;
}

export interface Panel {
  background: Background;
  accent: string;
  layers: Layer[];
}

export interface Theme {
  schema_version: number;
  id: string;
  name: string;
  panels: Panel[];
}

export interface DeviceSummary {
  configured: boolean;
  host: string | null;
  port: number;
  protocol: "hw400" | "hw402";
  local_token_set: boolean;
  name: string | null;
  device_id: number | null;
}

export interface PausedPanel {
  panel: number;
  source: "external" | "manual";
  reason: string;
  since: number;
}

export interface ExternalWatchStatus {
  enabled: boolean;
  ok: boolean;
  last_checked: number | null;
  message: string | null;
}

export interface Settings {
  refresh_interval: number;
  push_interval: number;
  allow_lan: boolean;
  auto_push: boolean;
  external_watch: boolean;
  external_check_interval: number;
  autostart: boolean;
  temperature_unit: "c" | "f";
}

export interface SystemInfo {
  version: string;
  autostart: boolean;
  autostart_supported: boolean;
  frozen: boolean;
  data_dir: string;
  auto_push: boolean;
  push_interval: number;
  last_push_at: number | null;
  skipped_frames: number;
  paused_panels: PausedPanel[];
  external_watch: ExternalWatchStatus;
}

export interface PresetMeta {
  id: string;
  name: string;
  description: string;
}

export interface ProbeOutcome {
  host: string;
  port: number;
  protocol: "hw400" | "hw402";
  ok: boolean;
  kind: string;
  message: string;
  raw: string | null;
  device_name: string | null;
}

export interface SendResult {
  panel: number;
  ok: boolean;
  pic_id: number;
  bytes: number;
  reply: Record<string, unknown>;
}

export interface SensorValues {
  [metric: string]: number | null;
}

export type WireStatus = "connecting" | "live" | "offline";
