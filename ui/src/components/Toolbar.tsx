import { useState } from "react";
import type { DeviceSummary, PresetMeta, WireStatus } from "../types";
import { DisplayIcon, GearIcon, HelpIcon, LogoIcon, SendIcon } from "./icons";

interface Props {
  presets: PresetMeta[];
  device: DeviceSummary | null;
  wire: WireStatus;
  sending: boolean;
  saveState: "idle" | "saving" | "saved" | "error";
  onPreset: (id: string) => void;
  onSend: () => void;
  onWizard: () => void;
  onDiagnostics: () => void;
  onSettings: () => void;
  onHelp: () => void;
}

const SAVE_LABEL: Record<Props["saveState"], string> = {
  idle: "",
  saving: "Saving…",
  saved: "Saved",
  error: "Not saved",
};

export default function Toolbar({
  presets,
  device,
  wire,
  sending,
  saveState,
  onPreset,
  onSend,
  onWizard,
  onDiagnostics,
  onSettings,
  onHelp,
}: Props) {
  const [choice, setChoice] = useState("");

  const applyTheme = () => {
    if (!choice) return;
    onPreset(choice);
    setChoice("");
  };

  return (
    <header className="topbar">
      <div className="app-name">
        <LogoIcon />
        <h1>Gate Theme Studio</h1>
      </div>

      <div className="theme-select">
        <select
          value={choice}
          aria-label="Theme to apply to all panels"
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value="">Apply a theme…</option>
          {presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name}
            </option>
          ))}
        </select>
        <button type="button" className="button-small" onClick={applyTheme} disabled={!choice}>
          All panels
        </button>
      </div>

      <button type="button" className="button-quiet device-button" onClick={onWizard}>
        <DisplayIcon />
        <span>{device?.configured ? device.name ?? device.host : "Connect a display"}</span>
      </button>

      <div className="topbar-spacer" />

      <span className={`live-state live-${wire}`}>
        {wire === "live" ? "Preview updating" : wire === "connecting" ? "Starting preview…" : "Preview offline"}
      </span>
      <span className={`save-state save-${saveState}`}>{SAVE_LABEL[saveState]}</span>

      <button type="button" className="button-quiet icon-text" onClick={onHelp} title="How to use this">
        <HelpIcon />
        <span className="label-wide">Help</span>
      </button>
      <button type="button" className="button-quiet icon-text" onClick={onSettings} title="Settings">
        <GearIcon />
        <span className="label-wide">Settings</span>
      </button>
      <button type="button" className="button-quiet icon-text" onClick={onDiagnostics} title="Troubleshooting">
        <span className="label-wide">Troubleshooting</span>
      </button>
      <button type="button" className="button-primary" onClick={onSend} disabled={sending}>
        <SendIcon />
        {sending ? "Sending…" : "Send"}
      </button>
    </header>
  );
}
