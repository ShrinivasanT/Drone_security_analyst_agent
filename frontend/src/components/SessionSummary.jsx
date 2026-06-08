import { useState } from "react";
import { getSummary } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// On-demand LLM session briefing + headline + key stats.
export default function SessionSummary() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getSummary());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const actions = (
    <button
      onClick={load}
      className="rounded bg-slate-700 px-2 py-1 text-xs font-medium text-slate-100 hover:bg-slate-600"
    >
      {loading ? "…" : "Generate"}
    </button>
  );

  return (
    <Panel title="Session Summary" subtitle="GET /summary" actions={actions}>
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!data && !error && <p className="text-sm text-slate-500">Click “Generate” for a briefing.</p>}
      {data && (
        <div className="space-y-3 text-sm">
          {data.headline && (
            <p className="rounded bg-amber-900/30 px-3 py-2 font-semibold text-amber-200">{data.headline}</p>
          )}
          <p className="text-slate-300">{data.summary}</p>
          {data.stats && (
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat label="Frames" value={data.stats.frames} />
              <Stat label="Events" value={data.stats.events} />
              <Stat label="Alerts" value={data.stats.alerts} />
            </div>
          )}
          {data.stats?.alerts_by_rule && (
            <div className="text-xs text-slate-400">
              {Object.entries(data.stats.alerts_by_rule).map(([k, v]) => (
                <span key={k} className="mr-2 inline-block rounded bg-slate-800 px-2 py-0.5">
                  {k}: {v}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded bg-slate-800 py-2">
      <div className="text-xl font-bold text-slate-100">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
    </div>
  );
}
