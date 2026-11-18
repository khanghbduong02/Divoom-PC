import { useEffect, useState } from "react";
import { api } from "../api";
import type { Settings as SettingsModel, SystemInfo, UpdateInfo } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

function when(timestamp: number | null): string {
  if (!timestamp) return "not yet";
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - timestamp));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return new Date(timestamp * 1000).toLocaleTimeString();
}

export default function Settings({ open, onClose }: Props) {
  const [settings, setSettings] = useState<SettingsModel | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [interval, setIntervalText] = useState("2");
  const [watchInterval, setWatchInterval] = useState("5");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [installingUpdate, setInstallingUpdate] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const checkForUpdate = async () => {
    setCheckingUpdate(true);
    setUpdateError(null);
    try {
      setUpdate(await api.checkUpdate());
    } catch (caught) {
      setUpdate(null);
      setUpdateError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setCheckingUpdate(false);
    }
  };

  const installUpdate = async () => {
    setInstallingUpdate(true);
    setUpdateError(null);
    try {
      await api.installUpdate();
      setNote("Update downloaded. Gate Theme Studio will restart automatically.");
    } catch (caught) {
      setUpdateError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setInstallingUpdate(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void (async () => {
      try {
        const [config, info] = await Promise.all([api.getConfig(), api.getSystem()]);
        setSettings(config.settings);
        setIntervalText(String(config.settings.push_interval));
        setWatchInterval(String(config.settings.external_check_interval));
        setSystem(info);
        setError(null);
        setNote(null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    })();
    void checkForUpdate();
  }, [open]);

  if (!open) {
    return null;
  }

  const save = async (patch: Partial<SettingsModel>, message?: string) => {
    if (!settings) return;
    setBusy(true);
    setError(null);
    try {
      const reply = await api.putSettings(patch);
      setSettings(reply.settings);
      setSystem(await api.getSystem());
      setNote(
        message ??
          (reply.restart_required
            ? "Restart Gate Theme Studio for this network change to take effect."
            : null),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const toggleAutostart = async (enabled: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const reply = await api.setAutostart(enabled);
      setSettings((current) => (current ? { ...current, autostart: reply.autostart } : current));
      setSystem(await api.getSystem());
      setNote(reply.autostart ? "Starts automatically next time you sign in to Windows." : "No longer starting with Windows.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Settings" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h2>Settings</h2>
            <p className="hint">These apply to the background app, not just this page.</p>
          </div>
          <button type="button" className="button-quiet" onClick={onClose}>
            Close
          </button>
        </div>

        {!settings ? (
          <p className="hint" style={{ paddingTop: 16 }}>
            {error ?? "Loading…"}
          </p>
        ) : (
          <div className="steps">
            <section className="step">
              <h3>Keep the display updated</h3>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.auto_push}
                  disabled={busy}
                  onChange={(event) => void save({ auto_push: event.target.checked })}
                />
                <span>
                  Keep readings live on the display
                  <em>
                    Sensor values update in the design already applied. Layout and colour changes
                    wait for <strong>Apply</strong> or <strong>Send all</strong>.
                  </em>
                </span>
              </label>
              <div className="inline-row">
                <label htmlFor="push-interval">Update readings every</label>
                <input
                  id="push-interval"
                  type="number"
                  min={0.5}
                  max={60}
                  step={0.5}
                  value={interval}
                  disabled={busy || !settings.auto_push}
                  onChange={(event) => setIntervalText(event.target.value)}
                  onBlur={() => {
                    const value = Number(interval);
                    if (!Number.isFinite(value)) {
                      setIntervalText(String(settings.push_interval));
                      return;
                    }
                    const clamped = Math.min(60, Math.max(0.5, value));
                    setIntervalText(String(clamped));
                    if (clamped !== settings.push_interval) {
                      void save({ push_interval: clamped });
                    }
                  }}
                />
                <span className="hint">seconds</span>
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.native_stats}
                  disabled={busy || !settings.auto_push}
                  onChange={(event) => void save({ native_stats: event.target.checked })}
                />
                <span>
                  Native sensor updates
                  <em>
                    Sends readings as text on the Gate instead of re-uploading each panel.
                    Needs LAN access so the Gate can fetch the static background.
                  </em>
                </span>
              </label>
              {settings.native_stats && !settings.allow_lan && (
                <div className="settings-callout">
                  <p className="hint">
                    Native updates are paused. The Gate must fetch the panel background from this PC
                    over your local network. Until LAN access is on and Gate Theme Studio is
                    restarted, panels use regular image updates.
                  </p>
                  <button
                    type="button"
                    className="button-small"
                    disabled={busy}
                    onClick={() =>
                      void save(
                        { allow_lan: true },
                        "LAN access is on. Restart Gate Theme Studio for native panels to start.",
                      )
                    }
                  >
                    Allow LAN access
                  </button>
                </div>
              )}
            </section>

            <section className="step">
              <h3>Other apps</h3>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.restore_on_start}
                  disabled={busy}
                  onChange={(event) =>
                    void save({ restore_on_start: event.target.checked })
                  }
                />
                <span>
                  Restore my panels after the Gate restarts
                  <em>
                    When the app or the Gate starts again, take back screens the Divoom
                    app changed while the PC was off. Manual pauses stay paused.
                  </em>
                </span>
              </label>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.external_watch}
                  disabled={busy}
                  onChange={(event) => void save({ external_watch: event.target.checked })}
                />
                <span>
                  Pause screens changed by the Divoom app
                  <em>
                    Checks Divoom's cloud for the phone app's screen layout. When a screen changes,
                    Gate Theme Studio stops updating that screen until you resume it.
                  </em>
                </span>
              </label>
              <div className="inline-row">
                <label htmlFor="watch-interval">Check every</label>
                <input
                  id="watch-interval"
                  type="number"
                  min={2}
                  max={60}
                  step={1}
                  value={watchInterval}
                  disabled={busy || !settings.external_watch}
                  onChange={(event) => setWatchInterval(event.target.value)}
                  onBlur={() => {
                    const value = Number(watchInterval);
                    if (!Number.isFinite(value)) {
                      setWatchInterval(String(settings.external_check_interval));
                      return;
                    }
                    const clamped = Math.min(60, Math.max(2, value));
                    setWatchInterval(String(clamped));
                    if (clamped !== settings.external_check_interval) {
                      void save({ external_check_interval: clamped });
                    }
                  }}
                />
                <span className="hint">seconds</span>
              </div>
              {system?.external_watch && (
                <p className="hint">
                  {system.external_watch.enabled
                    ? system.external_watch.ok
                      ? `Watching Divoom's cloud — last checked ${when(
                          system.external_watch.last_checked,
                        )}.`
                      : `Watch unavailable: ${
                          system.external_watch.message ?? "not checked yet"
                        }. Screens are not paused automatically until it reconnects.`
                    : "The Divoom-app watch is off; use Pause on a panel to hand it over manually."}
                </p>
              )}
            </section>

            <section className="step">
              <h3>Temperatures</h3>
              <div className="inline-row">
                <label htmlFor="temp-unit">Show temperatures in</label>
                <select
                  id="temp-unit"
                  value={settings.temperature_unit}
                  disabled={busy}
                  onChange={(event) =>
                    void save({ temperature_unit: event.target.value as "c" | "f" })
                  }
                >
                  <option value="c">Celsius (°C)</option>
                  <option value="f">Fahrenheit (°F)</option>
                </select>
              </div>
              <p className="hint">Applies to every CPU and GPU temperature on all panels.</p>
            </section>

            <section className="step">
              <h3>Start with Windows</h3>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={system?.autostart ?? settings.autostart}
                  disabled={busy || system?.autostart_supported === false}
                  onChange={(event) => void toggleAutostart(event.target.checked)}
                />
                <span>
                  Run Gate Theme Studio when I sign in
                  <em>
                    {system?.autostart_supported === false
                      ? "Available in the Windows build only."
                      : "It starts hidden in the system tray and keeps the display live."}
                  </em>
                </span>
              </label>
            </section>

            <section className="step">
              <h3>LAN access</h3>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={settings.allow_lan}
                  disabled={busy}
                  onChange={(event) => void save({ allow_lan: event.target.checked })}
                />
                <span>
                  Allow LAN access (phones and other devices)
                  <em>
                    Lets the Gate fetch native backgrounds and lets phones on this network open
                    the editor. Only while you trust the network. Takes effect after a restart.
                  </em>
                </span>
              </label>
            </section>

            <section className="step">
              <h3>Updates</h3>
              {checkingUpdate ? (
                <p className="hint">Checking for updates…</p>
              ) : updateError ? (
                <p className="hint is-error">{updateError}</p>
              ) : update ? (
                <p className="hint">
                  {update.available
                    ? `Version ${update.latest_version} is available. You are running ${update.current_version}.`
                    : `You are running the latest version (${update.current_version}).`}
                </p>
              ) : (
                <p className="hint">Update status has not been checked yet.</p>
              )}
              <div className="inline-row">
                <button
                  type="button"
                  className="button-small"
                  disabled={checkingUpdate || installingUpdate}
                  onClick={() => void checkForUpdate()}
                >
                  Check again
                </button>
                {update?.available && (
                  <button
                    type="button"
                    className="button-primary button-small"
                    disabled={installingUpdate || !update.can_install}
                    onClick={() => void installUpdate()}
                  >
                    {installingUpdate ? "Updating…" : "Update & restart"}
                  </button>
                )}
              </div>
              {update && !update.install_supported && (
                <p className="hint">
                  In-app updates are available in the downloadable Windows app. This source
                  checkout can still check the latest version.
                </p>
              )}
            </section>

            <section className="step">
              <h3>About</h3>
              <dl className="facts">
                <dt>Version</dt>
                <dd>{system?.version ?? "—"}</dd>
                <dt>Last update</dt>
                <dd>{when(system?.last_push_at ?? null)}</dd>
                <dt>Running as</dt>
                <dd>{system?.frozen ? "Installed app" : "Source checkout"}</dd>
                <dt>Data folder</dt>
                <dd>
                  <code>{system?.data_dir ?? "—"}</code>
                </dd>
              </dl>
            </section>
          </div>
        )}

        {note && <p className="hint settings-note">{note}</p>}
        {error && <p className="hint settings-note is-error">{error}</p>}
        <p className="modal-footnote">
          Closing this browser tab does not stop the updates — the app keeps running in the
          notification area. Quit it from the tray icon when you want it to stop.
        </p>
      </div>
    </div>
  );
}
