import { useState } from "react";
import { searchFrames } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// Semantic frame search → grid of blob_url thumbnails. Click opens a metadata modal.
export default function FrameSearch() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  const run = async (e) => {
    e?.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchFrames(q, 12);
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel title="Frame Search" subtitle="pgvector">
      <form onSubmit={run} className="mb-3 flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='e.g. "white car at night"'
          className="flex-1 rounded bg-slate-800 px-3 py-1.5 text-sm text-slate-100 outline-none ring-slate-700 focus:ring-2"
        />
        <button
          type="submit"
          className="rounded bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
        >
          {loading ? "…" : "Search"}
        </button>
      </form>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {results.map((r) => (
          <button
            key={r.frame_id}
            onClick={() => setSelected(r)}
            className="group relative overflow-hidden rounded border border-slate-800"
          >
            <img src={r.blob_url} alt={r.object_type} className="h-24 w-full object-cover" />
            <div className="absolute inset-x-0 bottom-0 bg-black/60 px-1 py-0.5 text-left text-[10px] text-slate-200">
              {r.object_type} · {(r.similarity ?? 0).toFixed(2)}
            </div>
          </button>
        ))}
      </div>
      {!loading && results.length === 0 && (
        <p className="text-sm text-slate-500">Enter a query to search the frame index.</p>
      )}

      {selected && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setSelected(null)}
        >
          <div className="flex max-w-3xl gap-4 rounded-xl bg-slate-900 p-4" onClick={(e) => e.stopPropagation()}>
            <img src={selected.blob_url} alt="" className="max-h-[70vh] rounded object-contain" />
            <div className="w-56 text-sm text-slate-300">
              <h3 className="mb-2 font-semibold text-slate-100">{selected.object_type}</h3>
              <dl className="space-y-1 text-xs">
                <Row k="location" v={selected.location} />
                <Row k="action" v={selected.action} />
                <Row k="color" v={selected.color} />
                <Row k="similarity" v={(selected.similarity ?? 0).toFixed(4)} />
                <Row k="timestamp" v={selected.timestamp} />
              </dl>
              <p className="mt-2 text-xs text-slate-400">{selected.raw_description}</p>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-slate-500">{k}</dt>
      <dd className="truncate text-right text-slate-300">{String(v ?? "—")}</dd>
    </div>
  );
}
