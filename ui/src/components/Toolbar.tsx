import type { DeviceSummary, PresetMeta, Theme, WireStatus } from "../types";
import { DisplayIcon, LogoIcon, SendIcon } from "./icons";

interface Props {
  theme: Theme | null;
  presets: PresetMeta[];
  device: DeviceSummary | null;
  wire: WireStatus;
  sending: boolean;
  saveState: "idle" | "saving" | "saved" | "error";
  onPreset: (id: string) => void;
  onSend: () => void;
  onWizard: () => void;
  onDiagnostics: () => void;
}

const SAVE_LABEL: Record<Props["saveState"], string> = {
  idle: "",
  saving: "Saving…",
  saved: "Saved",
  error: "Not saved",
};

export default function Toolbar({
  theme,
  presets,
  device,
  wire,
  sending,
  saveState,
  onPreset,
  onSend,
  onWizard,
  onDiagnostics,
}: Props) {
  const presetId = theme?.id.startsWith("preset-") ? theme.id.replace("preset-", "") : "";

  return (
    <header className="topbar">
      <div className="app-name">
        <LogoIcon />
        <h1>Gate Theme Studio</h1>
      </div>

      <label className="theme-select">
        <span>Theme</span>
        <select value={presetId} onChange={(event) => onPreset(event.target.value)}>
          <option value="">Custom layout</option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name}
            </option>
          ))}
        </select>
      </label>

      <button type="button" className="button-quiet device-button" onClick={onWizard}>
        <DisplayIcon />
        <span>{device?.configured ? device.name ?? device.host : "Connect a display"}</span>
      </button>

      <div className="topbar-spacer" />

      <span className={`live-state live-${wire}`}>
        {wire === "live" ? "Preview updating" : wire === "connecting" ? "Starting preview…" : "Preview offline"}
      </span>
      <span className={`save-state save-${saveState}`}>{SAVE_LABEL[saveState]}</span>
      <button type="button" className="button-quiet" onClick={onDiagnostics}>
        Troubleshooting
      </button>
      <button type="button" className="button-primary" onClick={onSend} disabled={sending}>
        <SendIcon />
        {sending ? "Sending…" : "Send to display"}
      </button>
    </header>
  );
}
