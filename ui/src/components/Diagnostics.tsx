import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { METRICS } from "../types";
import type { DeviceSummary, SensorValues, SendResult } from "../types";

function metricLabel(key: string): string {
  return METRICS.find((metric) => metric.key === key)?.label ?? key;
}

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Report {
  device: DeviceSummary;
  last_replies: SendResult[];
  last_error: { kind: string; message: string; raw: string | null; hint: string | null } | null;
  sensors: SensorValues;
  data_dir: string;
  hardware: {
    nvidia: boolean;
    cpu_temp_source: string | null;
    cpu_temp_hint: string | null;
  };
}

export default function Diagnostics({ open, onClose }: Props) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await api.diagnostics());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void load();
    }
  }, [open, load]);

  if (!open) {
    return null;
  }

  return (
    <aside className="drawer" aria-label="Troubleshooting">
      <div className="drawer-head">
        <h2>Troubleshooting</h2>
        <div className="inline-row">
          <button type="button" className="button-small" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" className="button-quiet" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      {error && <div className="notice notice-error">{error}</div>}

      {report && (
        <div className="drawer-body">
          <section>
            <h3>Display</h3>
            <dl className="facts">
              <div className="fact-row">
                <dt>Connected</dt>
                <dd>{report.device.configured ? "Yes" : "Not set up yet"}</dd>
              </div>
              {report.device.host && (
                <div className="fact-row">
                  <dt>Address</dt>
                  <dd>
                    {report.device.host}:{report.device.port}
                  </dd>
                </div>
              )}
              {report.device.configured && (
                <div className="fact-row">
                  <dt>Access token</dt>
                  <dd>{report.device.local_token_set ? "Set" : "Not needed"}</dd>
                </div>
              )}
            </dl>
            <p className="hint" style={{ marginTop: 8 }}>
              Settings and themes are stored in {report.data_dir}
            </p>
          </section>

          <section>
            <h3>Last error</h3>
            {report.last_error ? (
              <div className="notice notice-error">
                <strong>{report.last_error.message}</strong>
                {report.last_error.hint && <p>{report.last_error.hint}</p>}
              </div>
            ) : (
              <p className="hint">No errors.</p>
            )}
          </section>

          <section>
            <h3>Sensors</h3>
            <dl className="facts">
              {Object.entries(report.sensors).map(([key, value]) => (
                <div key={key} className="fact-row">
                  <dt>{metricLabel(key)}</dt>
                  <dd>{value === null ? "Not available" : String(value)}</dd>
                </div>
              ))}
            </dl>
            {report.sensors.cpu_temp === null && report.hardware.cpu_temp_hint && (
              <>
                <p className="hint" style={{ marginTop: 8 }}>
                  {report.hardware.cpu_temp_hint}
                </p>
                <a
                  className="button-small download-link"
                  href="https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"
                  target="_blank"
                  rel="noreferrer"
                >
                  Get LibreHardwareMonitor
                </a>
              </>
            )}
            {report.hardware.cpu_temp_source && (
              <p className="hint" style={{ marginTop: 8 }}>
                CPU temperature comes from {report.hardware.cpu_temp_source}.
              </p>
            )}
          </section>

          <section>
            <h3>What the display received</h3>
            {report.last_replies.length ? (
              <details className="raw-details" open>
                <summary>Last {report.last_replies.length} panel payload(s)</summary>
                <pre>{JSON.stringify(report.last_replies, null, 2)}</pre>
              </details>
            ) : (
              <p className="hint">Nothing has been sent yet.</p>
            )}
          </section>
        </div>
      )}
    </aside>
  );
}
