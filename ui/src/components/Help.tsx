import { useEffect, useState } from "react";
import { api, authToken } from "../api";
import type { SystemInfo } from "../types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function Help({ open, onClose }: Props) {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) return;
    void api
      .getSystem()
      .then(setSystem)
      .catch(() => setSystem(null));
    setCopied(false);
  }, [open]);

  if (!open) {
    return null;
  }

  const editorLink = `${window.location.origin}/?token=${encodeURIComponent(authToken)}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(editorLink);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="modal help-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Getting started"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2>Getting started</h2>
            <p className="hint">Everything you need to get a Gate on your desk and keep it live.</p>
          </div>
          <button type="button" className="button-quiet" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="steps">
          <section className="step">
            <h3>1. Start the app</h3>
            <p>
              Double-click <code>GateThemeStudio.exe</code>. There is no installer and nothing else
              to download: the window that opens is this editor, and a small icon appears in the
              notification area (bottom-right of the taskbar).
            </p>
            <p className="hint">
              Lost the window? Click the tray icon and choose <em>Open editor</em>. If the app is
              already running, double-clicking the exe just reopens this page.
            </p>
          </section>

          <section className="step">
            <h3>2. Connect the display</h3>
            <ol className="numbered">
              <li>Put the Times Gate on the same Wi-Fi as this PC and keep it powered on.</li>
              <li>
                The Divoom phone app can stay open. If it changes a screen, this app pauses that
                screen instead of overwriting it.
              </li>
              <li>
                Click <em>Connect a display</em> in the top bar, press <em>Find displays</em>, and
                pick the Gate that appears.
              </li>
              <li>That is permanent: the app reconnects by itself from now on.</li>
            </ol>
          </section>

          <section className="step">
            <h3>3. Make it yours</h3>
            <p>
              Pick a panel on the left, then add a reading from the metric list or a text label. Drag
              anything on the panel to move it, drag a corner to resize it, and drag the dots beside a
              panel to reorder panels. A theme fills all five panels at once and you can still tweak
              each one afterwards.
            </p>
            <p className="hint">
              Edits are saved as you type but stay in the editor until you send them: use{" "}
              <strong>Apply</strong> in the right panel to update only the selected screen, or{" "}
              <strong>Send all</strong> in the top bar for all edited panels. Panels you have not
              given layers or a background to are left as they are, so an empty default panel
              cannot blank a screen you already set up. The design already on the Gate keeps its
              sensor readings live. Every reading can be a big value, a progress bar, or a line
              graph of the last 5 minutes to 3 hours, and temperatures can be shown in Celsius or
              Fahrenheit from Settings.
            </p>
            <p className="hint">
              If you change a screen from the Divoom app, Gate Theme Studio notices within a few
              seconds and pauses that screen so the two do not fight. Press <strong>Resume</strong>{" "}
              in the right panel when you want it back, or <strong>Apply</strong> to take the screen
              back immediately. You can also pause a screen yourself from the same panel. This watch
              uses Divoom's cloud and can be turned off in Settings.
            </p>
          </section>

          <section className="step">
            <h3>4. Keep it running</h3>
            <p>
              The app starts with Windows by default (toggle it in <em>Settings</em>) and lives in
              the tray. Closing the browser tab does not stop it. To stop everything, right-click the
              tray icon and choose <em>Quit Gate Theme Studio</em>.
            </p>
          </section>

          <section className="step">
            <h3>Use it from your phone</h3>
            <p>
              Turn on <em>Settings → Let other devices on my network open the editor</em> and restart
              the app. It then prints a phone address; open that link on a device on the same Wi-Fi.
              The link includes a key, so treat it like a password.
            </p>
            <div className="inline-row">
              <button type="button" className="button-small" onClick={() => void copyLink()}>
                {copied ? "Copied" : "Copy this editor link"}
              </button>
              <span className="hint">Works on this PC right away.</span>
            </div>
          </section>

          <section className="step">
            <h3>If something looks wrong</h3>
            <p>
              Panels stuck on “loading” or the display not changing? Open <em>Troubleshooting</em> in
              the top bar: it shows the last reply from the display and what to try. If a panel says
              <em>updates paused</em>, the Divoom app changed it; press <strong>Resume</strong> or{" "}
              <strong>Apply</strong> when you want this app to own it again.
            </p>
            <p>
              CPU temperature stays at <code>--</code>? Windows does not let normal apps read it.
              Open <em>Troubleshooting</em> and press <strong>Enable CPU temperature</strong>, then
              approve the one Windows prompt. It installs the signed sensor driver, switches on
              LibreHardwareMonitor's local server, and starts it at every login; the reading appears
              within half a minute. NVIDIA GPU readings use the driver and need no helper;
              AMD and Intel GPU readings use LibreHardwareMonitor.
            </p>
            {system && (
              <p className="hint">
                Version {system.version} · data folder <code>{system.data_dir}</code>
              </p>
            )}
            <p className="hint">
              Building this from source? The README has the commands and the one-file Windows build.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
