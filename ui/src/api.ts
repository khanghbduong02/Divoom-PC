import type {
  DeviceSummary,
  PausedPanel,
  PresetMeta,
  ProbeOutcome,
  SavedItem,
  SavedLibrary,
  SendResult,
  SensorValues,
  Settings,
  SystemInfo,
  Theme,
} from "./types";

const TOKEN_KEY = "gate-studio-token";

function initialToken(): string {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("token");
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl);
    url.searchParams.delete("token");
    window.history.replaceState({}, "", url.toString());
    return fromUrl;
  }
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export const authToken = initialToken();

export class ApiFailure extends Error {
  status: number;
  kind?: string;
  raw?: string | null;
  hint?: string | null;

  constructor(
    status: number,
    message: string,
    kind?: string,
    raw?: string | null,
    hint?: string | null,
  ) {
    super(message);
    this.name = "ApiFailure";
    this.status = status;
    this.kind = kind;
    this.raw = raw;
    this.hint = hint;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${authToken}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const body = payload as { error?: { message?: string; kind?: string; raw?: string; hint?: string }; detail?: string } | null;
    const error = body?.error;
    throw new ApiFailure(
      response.status,
      error?.message ?? body?.detail ?? `Request failed (${response.status})`,
      error?.kind,
      error?.raw,
      error?.hint,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  getTheme: () => request<{ theme: Theme }>("/api/theme"),
  putTheme: (theme: Theme) =>
    request<{ theme: Theme }>("/api/theme", { method: "PUT", body: JSON.stringify(theme) }),
  getPresets: () => request<{ presets: PresetMeta[] }>("/api/presets"),
  applyPreset: (id: string, panel?: number) =>
    request<{ theme: Theme }>(`/api/presets/${id}/apply`, {
      method: "POST",
      body: JSON.stringify({ panel: panel ?? null }),
    }),
  getLibrary: () => request<SavedLibrary>("/api/library"),
  saveTheme: (name: string) =>
    request<{ item: SavedItem; library: SavedLibrary }>("/api/library/themes", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  savePanel: (panel: number, name: string) =>
    request<{ item: SavedItem; library: SavedLibrary }>("/api/library/panels", {
      method: "POST",
      body: JSON.stringify({ panel, name }),
    }),
  applySavedTheme: (id: string) =>
    request<{ theme: Theme }>(`/api/library/themes/${id}/apply`, { method: "POST" }),
  applySavedPanel: (id: string, panel: number) =>
    request<{ theme: Theme }>(`/api/library/panels/${id}/apply`, {
      method: "POST",
      body: JSON.stringify({ panel }),
    }),
  getConfig: () =>
    request<{ device: DeviceSummary; settings: Settings; data_dir: string; media_dir: string }>(
      "/api/config",
    ),
  putSettings: (patch: Partial<Settings>) =>
    request<{ settings: Settings; restart_required: boolean; autostart?: boolean }>(
      "/api/config/settings",
      { method: "PUT", body: JSON.stringify(patch) },
    ),
  getSystem: () => request<SystemInfo>("/api/system"),
  installSensors: () =>
    request<{ started: boolean }>("/api/system/sensors/install", { method: "POST" }),
  setAutostart: (enabled: boolean) =>
    request<{ autostart: boolean; supported: boolean }>("/api/system/autostart", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  probe: (host: string, localToken: number | null) =>
    request<{ outcomes: ProbeOutcome[] }>("/api/device/probe", {
      method: "POST",
      body: JSON.stringify({ host, local_token: localToken }),
    }),
  discover: (host: string, localToken: number | null) =>
    request<{
      cloud: { name: string; ip: string; mac: string }[];
      scan: ProbeOutcome[];
      errors: string[];
    }>("/api/device/discover", {
      method: "POST",
      body: JSON.stringify({ host: host || null, local_token: localToken }),
    }),
  connectDevice: (body: {
    host: string;
    port: number;
    protocol: "hw400" | "hw402";
    local_token: number | null;
  }) =>
    request<{ device: DeviceSummary; reply: Record<string, unknown> }>("/api/device/connect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  testFrame: (panel: number) =>
    request<{ results: SendResult[] }>("/api/device/test-frame", {
      method: "POST",
      body: JSON.stringify({ panel }),
    }),
  send: (panels?: number[]) =>
    request<{ results: SendResult[] }>("/api/send", {
      method: "POST",
      body: JSON.stringify({ panels: panels ?? null }),
    }),
  setPanelPaused: (
    panel: number,
    paused: boolean,
    source: "external" | "manual" = "manual",
    reason = "",
  ) =>
    request<{ paused_panels: PausedPanel[] }>(`/api/panels/${panel}/pause`, {
      method: "POST",
      body: JSON.stringify({ paused, source, reason }),
    }),
  getSensors: () => request<{ values: SensorValues }>("/api/sensors"),
  diagnostics: () =>
    request<{
      device: DeviceSummary;
      last_replies: SendResult[];
      last_error: { kind: string; message: string; raw: string | null; hint: string | null } | null;
      sensors: SensorValues;
      data_dir: string;
      auto_push: boolean;
      last_push_at: number | null;
      skipped_frames: number;
      temperature_unit: "c" | "f";
      hardware: {
        nvidia: boolean;
        cpu_temp_source: string | null;
        cpu_temp_hint: string | null;
      };
    }>("/api/diagnostics"),
  uploadMedia: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ name: string; url: string }>("/api/media", { method: "POST", body: form });
  },
};

export function wsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}/ws?token=${encodeURIComponent(authToken)}`;
}

export function mediaUrl(name: string): string {
  return `/media/${encodeURIComponent(name)}?token=${encodeURIComponent(authToken)}`;
}
