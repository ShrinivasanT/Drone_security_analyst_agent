import { useEffect, useState } from "react";
import { getAlerts, severityClasses } from "../api.js";

// Polls unresolved alerts every 2s. Shows the most recent triggering frame + message,
// with a strip of other active alerts below.
export default function AlertBanner() {
  const [alerts, setAlerts] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const data = await getAlerts(true, 20);
        if (live) {
          setAlerts(data.alerts || []);
          setError(null);
        }
      } catch (e) {
        if (live) setError(e.message);
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-lg bg-slate-800 px-4 py-3 text-sm text-slate-400">
        Alerts unavailable: {error}
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="rounded-lg border border-emerald-700 bg-emerald-900/30 px-4 py-3 text-emerald-300">
        ✓ No active alerts — perimeter nominal
      </div>
    );
  }

  const top = alerts[0];
  return (
    <div className="rounded-lg border border-red-700 bg-red-950/60 p-4">
      <div className="flex items-start gap-4">
        {top.blob_url && (
          <img
            src={top.blob_url}
            alt="triggering frame"
            className="h-24 w-32 flex-none rounded object-cover ring-2 ring-red-600"
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="animate-pulse text-lg">🚨</span>
            <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${severityClasses(top.severity)}`}>
              {top.severity}
            </span>
            <span className="text-xs text-red-300">{top.rule}</span>
          </div>
          <p className="mt-1 truncate text-lg font-semibold text-red-100">{top.message}</p>
          <p className="text-xs text-red-300/70">
            {alerts.length} active alert{alerts.length > 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {alerts.length > 1 && (
        <div className="mt-3 flex gap-2 overflow-x-auto">
          {alerts.slice(1, 10).map((a) => (
            <div key={a.id} className="flex-none rounded bg-red-900/50 px-2 py-1 text-xs text-red-200">
              <span className="font-mono">{a.metadata?.time || ""}</span> {a.rule}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
