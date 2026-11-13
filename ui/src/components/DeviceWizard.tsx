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
            ? "Found a device on the network — pick it below."
            : "No device answered on this network. Enter the IP shown in the Divoom app.",
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
      setNotice({ tone: "error", text: "Enter the device IP address first." });
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
          text: `${ok.device_name ?? "Times Gate"} answered on port ${ok.port}.`,
        });
        setRaw(ok.raw);
      } else {
        setNotice({
          tone: "error",
          text: reply.outcomes.map((outcome) => `${outcome.port}: ${outcome.message}`).join(" · "),
        });
        setRaw(reply.outcomes.map((outcome) => `port ${outcome.port} (${outcome.protocol})\n${outcome.raw ?? "no reply"}`).join("\n\n"));
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
        text: `Saved ${reply.device.host}:${reply.device.port}. Now send a test tile.`,
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
        text: `Test tile sent to panel ${panel + 1}. It should show a framed number on the device.`,
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
    <div className="overlay" role="dialog" aria-modal="true">
      <div className="wizard">
        <header>
          <h2>Connect your Times Gate</h2>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <ol className="steps">
          <li>
            <h3>1 · Find the device</h3>
            <p className="help">
              Same Wi-Fi as this PC. The device needs internet once after booting before its
              local API answers.
            </p>
            <div className="inline">
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
              <ul className="found">
                {found.map((entry) => (
                  <li key={entry.ip}>
                    <button type="button" onClick={() => setHost(entry.ip)}>
                      {entry.name} · {entry.ip}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>

          <li>
            <h3>2 · Probe both hardware revisions</h3>
            <p className="help">
              HW 400 answers on port 80, HW 402 on port 9000. Probing tells us which one your
              unit is without guessing.
            </p>
            <div className="inline">
              <button type="button" onClick={probe} disabled={busy !== null}>
                {busy === "probe" ? "Probing…" : "Probe ports 80 and 9000"}
              </button>
            </div>

            {outcomes.length > 0 && (
              <table className="probe-table">
                <thead>
                  <tr>
                    <th>Port</th>
                    <th>Result</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {outcomes.map((outcome) => (
                    <tr key={`${outcome.port}-${outcome.protocol}`}>
                      <td>{outcome.port}</td>
                      <td>
                        <span className={`badge badge-${outcome.kind}`}>{outcome.kind}</span>
                        <span className="probe-message">{outcome.message}</span>
                      </td>
                      <td>
                        <button
                          type="button"
                          onClick={() => connect(outcome)}
                          disabled={busy !== null || !(outcome.ok || outcome.kind === "token")}
                        >
                          Use this port
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </li>

          <li>
            <h3>3 · LocalToken</h3>
            <p className="help">
              Newer firmware rejects local calls without it. Open the Divoom app → device
              settings → copy the token number. Leave empty if your unit does not need one.
            </p>
            <input
              type="text"
              inputMode="numeric"
              placeholder="e.g. 123456789"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
            />
          </li>

          <li>
            <h3>4 · Prove it on the hardware</h3>
            <p className="help">Send a numbered tile to one panel. Success means a coloured square appears.</p>
            <div className="inline">
              <select value={panel} onChange={(event) => setPanel(Number(event.target.value))}>
                {[0, 1, 2, 3, 4].map((index) => (
                  <option key={index} value={index}>
                    Panel {index + 1}
                  </option>
                ))}
              </select>
              <button type="button" onClick={sendTest} disabled={busy !== null || !device?.configured}>
                {busy === "test" ? "Sending…" : "Send test tile"}
              </button>
            </div>
            {results && (
              <p className="help">
                {results.length} panel(s) accepted · {results.reduce((sum, item) => sum + item.bytes, 0)} bytes
              </p>
            )}
          </li>
        </ol>

        {notice && (
          <div className={`notice notice-${notice.tone}`}>
            <strong>{notice.text}</strong>
            {notice.hint && <p>{notice.hint}</p>}
          </div>
        )}

        {raw && <pre className="raw">{raw}</pre>}

        <footer className="notes">
          <p>
            Only one controller per device: close the Divoom app while this is pushing, or the
            panels will flicker between two writers.
          </p>
        </footer>
      </div>
    </div>
  );
}
