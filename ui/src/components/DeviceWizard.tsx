import { useEffect, useState } from "react";
import { ApiFailure, api } from "../api";
import type { DeviceSummary, ProbeOutcome, SendResult } from "../types";

interface Props {
  open: boolean;
  device: DeviceSummary | null;
  onClose: () => void;
  onChanged: () => void;
}

interface Notice {
  tone: "ok" | "error" | "info";
  text: string;
  hint?: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "Connected",
  token: "Needs token",
  refused: "Nothing there",
  timeout: "No answer",
  network: "Unreachable",
  device: "Error reply",
  unknown: "Unknown",
};

function statusLabel(kind: string): string {
  return STATUS_LABEL[kind] ?? kind;
}

function describe(error: unknown): Notice {
  if (error instanceof ApiFailure) {
    return { tone: "error", text: error.message, hint: error.hint };
  }
  return { tone: "error", text: error instanceof Error ? error.message : String(error) };
}

export default function DeviceWizard({ open, device, onClose, onChanged }: Props) {
  const [host, setHost] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [found, setFound] = useState<{ name: string; ip: string }[]>([]);
  const [outcomes, setOutcomes] = useState<ProbeOutcome[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [raw, setRaw] = useState<string | null>(null);
  const [busy, setBusy] = useState<null | "scan" | "probe" | "connect" | "test">(null);
  const [panel, setPanel] = useState(0);
  const [results, setResults] = useState<SendResult[] | null>(null);

  useEffect(() => {
    if (open) {
      setHost(device?.host ?? "");
      setNotice(null);
      setRaw(null);
      setResults(null);
    }
  }, [open, device?.host]);

  if (!open) {
    return null;
  }

  const parsedToken = tokenInput.trim() === "" ? null : Number(tokenInput.trim());
  const token = parsedToken === null || Number.isNaN(parsedToken) ? null : parsedToken;

  const scanNetwork = async () => {
    setBusy("scan");
    setNotice(null);
    try {
      const reply = await api.discover(host.trim(), token);
      setFound(reply.cloud.map((entry) => ({ name: entry.name || "Times Gate", ip: entry.ip })));
      if (reply.scan.length) {
        setOutcomes(reply.scan);
      }
      setNotice({
        tone: reply.cloud.length || reply.scan.length ? "ok" : "info",
        text:
          reply.cloud.length || reply.scan.length
            ? "Found a display on your network. Pick it below."
            : "No display answered. Type the IP address shown in the Divoom app.",
      });
      setRaw(reply.errors.length ? reply.errors.join("\n") : null);
    } catch (error) {
      setNotice(describe(error));
    } finally {
      setBusy(null);
    }
  };

  const probe = async () => {
    const target = host.trim();
    if (!target) {
      setNotice({ tone: "error", text: "Enter the display's IP address first." });
      return;
    }
    setBusy("probe");
    setNotice(null);
    try {
      const reply = await api.probe(target, token);
      setOutcomes(reply.outcomes);
      const ok = reply.outcomes.find((outcome) => outcome.ok);
      if (ok) {
        setNotice({
          tone: "ok",
          text: `${ok.device_name ?? "Your display"} answered on port ${ok.port}.`,
        });
        setRaw(ok.raw);
      } else {
        setNotice({
          tone: "error",
          text: reply.outcomes.map((outcome) => `${outcome.port}: ${outcome.message}`).join(" · "),
        });
        setRaw(
          reply.outcomes
            .map((outcome) => `port ${outcome.port} (${outcome.protocol})\n${outcome.raw ?? "no reply"}`)
            .join("\n\n"),
        );
      }
    } catch (error) {
      setNotice(describe(error));
    } finally {
      setBusy(null);
    }
  };

  const connect = async (outcome: ProbeOutcome) => {
    setBusy("connect");
    setNotice(null);
    try {
      const reply = await api.connectDevice({
        host: outcome.host,
        port: outcome.port,
        protocol: outcome.protocol,
        local_token: token,
      });
      setNotice({
        tone: "ok",
        text: `Saved ${reply.device.host}:${reply.device.port}. Send a test image in step 4.`,
      });
      setRaw(JSON.stringify(reply.reply, null, 2));
      onChanged();
    } catch (error) {
      setNotice(describe(error));
    } finally {
      setBusy(null);
    }
  };

  const sendTest = async () => {
    setBusy("test");
    setNotice(null);
    try {
      const reply = await api.testFrame(panel);
      setResults(reply.results);
      setNotice({
        tone: "ok",
        text: `Test image sent to panel ${panel + 1}. It should show a framed number.`,
      });
      setRaw(JSON.stringify(reply.results, null, 2));
      onChanged();
    } catch (error) {
      setNotice(describe(error));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Connect a display">
      <div className="modal">
        <div className="modal-head">
          <div>
            <h2>Connect a display</h2>
            <p className="hint">
              The display must be on the same Wi-Fi as this computer, and it needs to have
              been online once since it was last powered on.
            </p>
          </div>
          <button type="button" className="button-quiet" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="steps">
          <section className="step">
            <h3>1. Find the display</h3>
            <p className="hint">Scan your network, or type the IP the Divoom app shows.</p>
            <div className="inline-row">
              <input
                type="text"
                placeholder="192.168.1.42"
                value={host}
                onChange={(event) => setHost(event.target.value)}
              />
              <button type="button" onClick={scanNetwork} disabled={busy !== null}>
                {busy === "scan" ? "Scanning…" : "Scan network"}
              </button>
            </div>
            {found.length > 0 && (
              <ul className="found-list">
                {found.map((entry) => (
                  <li key={entry.ip}>
                    <button type="button" className="button-small" onClick={() => setHost(entry.ip)}>
                      {entry.name} — {entry.ip}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="step">
            <h3>2. Check both connection types</h3>
            <p className="hint">
              Times Gate units use one of two ports depending on the hardware revision. This
              checks both so you don't have to guess.
            </p>
            <div className="inline-row">
              <button type="button" onClick={probe} disabled={busy !== null}>
                {busy === "probe" ? "Checking…" : "Check port 80 and 9000"}
              </button>
            </div>

            {outcomes.length > 0 && (
              <ul className="probe-list">
                {outcomes.map((outcome) => (
                  <li key={`${outcome.port}-${outcome.protocol}`} className="probe-row">
                    <span className="probe-port">Port {outcome.port}</span>
                    <span className={`status-chip status-${outcome.kind}`}>
                      {statusLabel(outcome.kind)}
                    </span>
                    <span className="probe-message">{outcome.message}</span>
                    <button
                      type="button"
                      className="button-small"
                      onClick={() => connect(outcome)}
                      disabled={busy !== null || !(outcome.ok || outcome.kind === "token")}
                    >
                      Use this
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="step">
            <h3>3. Access token (only if your unit asks for one)</h3>
            <p className="hint">
              Newer firmware rejects local requests without it. In the Divoom app, open the
              display's settings and copy the token number. Otherwise leave this empty.
            </p>
            <input
              type="text"
              inputMode="numeric"
              placeholder="Optional"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
            />
          </section>

          <section className="step">
            <h3>4. Send a test image</h3>
            <p className="hint">A framed number should appear on the panel you choose.</p>
            <div className="inline-row">
              <select value={panel} onChange={(event) => setPanel(Number(event.target.value))}>
                {[0, 1, 2, 3, 4].map((index) => (
                  <option key={index} value={index}>
                    Panel {index + 1}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={sendTest}
                disabled={busy !== null || !device?.configured}
              >
                {busy === "test" ? "Sending…" : "Send test image"}
              </button>
            </div>
            {results && (
              <p className="hint">
                Accepted by {results.length} panel(s) ·{" "}
                {results.reduce((sum, item) => sum + (item.bytes ?? 0), 0)} bytes sent
              </p>
            )}
          </section>
        </div>

        {notice && (
          <div className={`notice notice-${notice.tone}`}>
            <strong>{notice.text}</strong>
            {notice.hint && <p>{notice.hint}</p>}
          </div>
        )}

        {raw && (
          <details className="raw-details">
            <summary>Show the display's reply</summary>
            <pre>{raw}</pre>
          </details>
        )}

        <p className="modal-footnote">
          Tip: the Divoom phone app can stay open. If it changes a screen, Gate Theme Studio
          pauses that screen to avoid a fight; resume it from the inspector when you want it back.
        </p>
      </div>
    </div>
  );
}
