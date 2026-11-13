import type {
  DeviceSummary,
  PresetMeta,
  ProbeOutcome,
  SendResult,
  SensorValues,
  Settings,
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
  applyPreset: (id: string) =>
    request<{ theme: Theme }>(`/api/presets/${id}/apply`, { method: "POST" }),
  getConfig: () =>
    request<{ device: DeviceSummary; settings: Settings; data_dir: string; media_dir: string }>(
      "/api/config",
    ),
  putSettings: (patch: Partial<Settings>) =>
    request<{ settings: Settings; restart_required: boolean }>("/api/config/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
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
  getSensors: () => request<{ values: SensorValues }>("/api/sensors"),
  diagnostics: () =>
    request<{
      device: DeviceSummary;
      last_replies: SendResult[];
      last_error: { kind: string; message: string; raw: string | null; hint: string | null } | null;
      sensors: SensorValues;
      data_dir: string;
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
