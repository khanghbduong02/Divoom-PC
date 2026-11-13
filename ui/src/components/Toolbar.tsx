import type { DeviceSummary, PresetMeta, Theme, WireStatus } from "../types";

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
  saving: "saving…",
  saved: "saved",
  error: "save failed",
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
    <header className="toolbar">
      <div className="brand">
        GATE<span>THEME STUDIO</span>
      </div>

      <label className="preset-picker">
        <span>Preset</span>
        <select value={presetId} onChange={(event) => onPreset(event.target.value)}>
          <option value="">Custom</option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name}
            </option>
          ))}
        </select>
      </label>

      <button type="button" className="ghost device-chip" onClick={onWizard}>
        <span className={`dot ${device?.configured ? "dot-on" : "dot-off"}`} />
        {device?.configured
          ? `${device.name ?? "Times Gate"} · ${device.host}:${device.port}`
          : "Connect device"}
      </button>

      <span className={`wire wire-${wire}`}>
        {wire === "live" ? "live preview" : wire}
      </span>

      <div className="spacer" />

      <span className={`save-state save-${saveState}`}>{SAVE_LABEL[saveState]}</span>
      <button type="button" className="ghost" onClick={onDiagnostics}>
        Diagnostics
      </button>
      <button type="button" className="primary" onClick={onSend} disabled={sending}>
        {sending ? "Sending…" : "Send to device"}
      </button>
    </header>
  );
}
