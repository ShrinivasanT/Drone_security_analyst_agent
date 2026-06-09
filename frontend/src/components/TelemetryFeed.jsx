import { useEffect, useState } from "react";
import { getFrames } from "../api.js";

// Live scrolling feed of every ingested frame (polls every 2s), thumbnail per row.
// Unlike the Event Log, this lists ALL frames — an upload with no alert still appears.
export default function TelemetryFeed() {
  const [frames, setFrames] = useState([]);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const data = await getFrames(10);
        if (live) setFrames(data.frames || []);
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
        {frames.map((f) => {
          const time = (f.telemetry && f.telemetry.time) || "";
          return (
            <li key={f.id} className="flex items-center gap-3 rounded bg-slate-800/60 p-2">
              {f.blob_url && (
                <img src={f.blob_url} alt="" className="h-10 w-14 flex-none rounded object-cover" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-slate-700 px-1.5 text-[10px] font-bold uppercase text-slate-200">
                    {f.object_type || "frame"}
                  </span>
                  <span className="truncate text-xs font-medium text-slate-300">
                    {f.location || "unknown"}
                  </span>
                  {time && <span className="ml-auto flex-none text-[10px] text-slate-500">{time}</span>}
                </div>
                <p className="truncate text-xs text-slate-400">
                  {f.raw_description || `${f.color || ""} ${f.object_type || ""} ${f.action || ""}`.trim()}
                </p>
              </div>
            </li>
          );
        })}
        {frames.length === 0 && <p className="text-sm text-slate-500">No frames yet.</p>}
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
