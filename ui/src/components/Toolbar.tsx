import { useState } from "react";
import type { DeviceSummary, PresetMeta, SavedItem, WireStatus } from "../types";
import { DisplayIcon, GearIcon, HelpIcon, LogoIcon, SendIcon } from "./icons";

interface Props {
  presets: PresetMeta[];
  savedThemes: SavedItem[];
  device: DeviceSummary | null;
  wire: WireStatus;
  sending: boolean;
  saveState: "idle" | "saving" | "saved" | "error";
  onPreset: (id: string) => void;
  onSavedTheme: (id: string) => void;
  onSaveTheme: () => void;
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
  savedThemes,
  device,
  wire,
  sending,
  saveState,
  onPreset,
  onSavedTheme,
  onSaveTheme,
  onSend,
  onWizard,
  onDiagnostics,
  onSettings,
  onHelp,
}: Props) {
  const [choice, setChoice] = useState("");

  const applyTheme = () => {
    if (!choice) return;
    if (choice.startsWith("saved:")) {
      onSavedTheme(choice.slice("saved:".length));
    } else if (choice.startsWith("preset:")) {
      onPreset(choice.slice("preset:".length));
    }
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
          <optgroup label="Built-in">
            {presets.map((preset) => (
              <option key={preset.id} value={`preset:${preset.id}`}>
                {preset.name}
              </option>
            ))}
          </optgroup>
          {savedThemes.length > 0 && (
            <optgroup label="Saved">
              {savedThemes.map((item) => (
                <option key={item.id} value={`saved:${item.id}`}>
                  {item.name}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <button type="button" className="button-small" onClick={applyTheme} disabled={!choice}>
          Apply
        </button>
        <button
          type="button"
          className="button-small"
          onClick={onSaveTheme}
          title="Save all five panels as a reusable theme"
        >
          Save theme
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
      <button
        type="button"
        className="button-primary"
        onClick={onSend}
        disabled={sending}
        title="Apply the current design to all five panels"
      >
        <SendIcon />
        {sending ? "Sending…" : "Send all"}
      </button>
    </header>
  );
}
