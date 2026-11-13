import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { DeviceSummary, SensorValues, SendResult } from "../types";

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
}

export default function Diagnostics({ open, onClose }: Props) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setReport(await api.diagnostics());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
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
    <aside className="diagnostics">
      <header>
        <h2>Diagnostics</h2>
        <div className="inline">
          <button type="button" onClick={() => void load()}>
            Refresh
          </button>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </header>

      {error && <div className="notice notice-error">{error}</div>}

      {report && (
        <>
          <h3>Device</h3>
          <pre className="raw">{JSON.stringify(report.device, null, 2)}</pre>

          <h3>Last error</h3>
          <pre className="raw">
            {report.last_error ? JSON.stringify(report.last_error, null, 2) : "none"}
          </pre>

          <h3>Last device replies</h3>
          <pre className="raw">
            {report.last_replies.length ? JSON.stringify(report.last_replies, null, 2) : "nothing sent yet"}
          </pre>

          <h3>Sensors</h3>
          <pre className="raw">{JSON.stringify(report.sensors, null, 2)}</pre>

          <h3>Data folder</h3>
          <pre className="raw">{report.data_dir}</pre>
        </>
      )}
    </aside>
  );
}
