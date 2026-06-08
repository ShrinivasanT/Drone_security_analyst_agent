import { useEffect, useState } from "react";
import { getEvents, severityClasses } from "../api.js";

// Live scrolling feed of the latest events (polls every 2s), thumbnail per row.
export default function TelemetryFeed() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const data = await getEvents(10);
        if (live) setEvents(data.events || []);
      } catch {
        /* transient */
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  return (
    <Panel title="Live Telemetry Feed" subtitle="latest 10 · 2s">
      <ul className="space-y-2">
        {events.map((e) => (
          <li key={e.id} className="flex items-center gap-3 rounded bg-slate-800/60 p-2">
            {e.blob_url && (
              <img src={e.blob_url} alt="" className="h-10 w-14 flex-none rounded object-cover" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 text-[10px] font-bold uppercase ${severityClasses(e.severity)}`}>
                  {e.severity}
                </span>
                <span className="truncate text-xs font-medium text-slate-200">{e.event_type}</span>
              </div>
              <p className="truncate text-xs text-slate-400">{e.description}</p>
            </div>
          </li>
        ))}
        {events.length === 0 && <p className="text-sm text-slate-500">No events yet.</p>}
      </ul>
    </Panel>
  );
}

export function Panel({ title, subtitle, children, actions }) {
  return (
    <section className="flex h-full flex-col rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">{title}</h2>
        {subtitle && <span className="text-xs text-slate-500">{subtitle}</span>}
        {actions}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}
