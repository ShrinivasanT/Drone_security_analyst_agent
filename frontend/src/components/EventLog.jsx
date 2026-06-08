import { Fragment, useEffect, useState } from "react";
import { getEvents, severityClasses } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// Full event log (polls every 5s). Rows expand to reveal the frame thumbnail + full text.
export default function EventLog() {
  const [events, setEvents] = useState([]);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let live = true;
    const tick = async () => {
      try {
        const data = await getEvents(50);
        if (live) setEvents(data.events || []);
      } catch {
        /* transient */
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);

  return (
    <Panel title="Event Log" subtitle={`${events.length} · 5s`}>
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-900 text-slate-500">
          <tr>
            <th className="py-1">Sev</th>
            <th className="py-1">Type</th>
            <th className="py-1">Description</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <Fragment key={e.id}>
              <tr
                onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                className="cursor-pointer border-t border-slate-800 hover:bg-slate-800/50"
              >
                <td className="py-1">
                  <span className={`rounded px-1.5 text-[10px] font-bold uppercase ${severityClasses(e.severity)}`}>
                    {e.severity}
                  </span>
                </td>
                <td className="py-1 pr-2 font-medium text-slate-300">{e.event_type}</td>
                <td className="truncate py-1 text-slate-400">{e.description}</td>
              </tr>
              {expanded === e.id && (
                <tr className="bg-slate-800/40">
                  <td colSpan={3} className="p-3">
                    <div className="flex gap-3">
                      {e.blob_url && (
                        <img src={e.blob_url} alt="" className="h-28 w-40 flex-none rounded object-cover" />
                      )}
                      <div className="text-xs text-slate-300">
                        <p className="mb-1">{e.description}</p>
                        <p className="text-slate-500">
                          {e.created_at} · frame: {e.frame_id || "—"}
                        </p>
                        {e.blob_url && (
                          <a href={e.blob_url} target="_blank" rel="noreferrer" className="text-sky-400 underline">
                            open full frame
                          </a>
                        )}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
      {events.length === 0 && <p className="text-sm text-slate-500">No events logged.</p>}
    </Panel>
  );
}
