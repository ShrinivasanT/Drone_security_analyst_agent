import { useState } from "react";
import { ingestVideo, severityClasses } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// Upload a video clip + synthetic-telemetry settings, run the video-level agent, and
// render the clip's single action verdict (alert decided across the whole clip, not per
// frame). Each frame is a Groq vision call, so ingestion is slow — show a spinner.
export default function VideoUpload({ onIngested }) {
  const [file, setFile] = useState(null);
  const [interval, setInterval] = useState(2);
  const [maxFrames, setMaxFrames] = useState(12);
  const [startTime, setStartTime] = useState("");
  const [location, setLocation] = useState("");
  const [seed, setSeed] = useState(42);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Choose a video file first.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("interval", String(interval));
      fd.append("max_frames", String(maxFrames));
      fd.append("seed", String(seed));
      if (startTime) fd.append("start_time", startTime);
      if (location) fd.append("location", location);
      const data = await ingestVideo(fd);
      setResult(data);
      onIngested?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const verdict = result?.verdict;

  return (
    <Panel title="Ingest Video" subtitle="video-level alert">
      <form onSubmit={submit} className="space-y-3">
        <input
          type="file"
          accept="video/*,.mp4,.avi,.mov,.mkv"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-sky-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-sky-500"
        />

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Field label="Interval (s)">
            <input
              type="number" min="0.2" step="0.1" value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Max frames">
            <input
              type="number" min="1" max="60" value={maxFrames}
              onChange={(e) => setMaxFrames(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Seed">
            <input
              type="number" value={seed}
              onChange={(e) => setSeed(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Start time (HH:MM)">
            <input
              type="text" placeholder="e.g. 22:30" value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className={inputCls}
            />
          </Field>
          <Field label="Location (optional)">
            <input
              type="text" placeholder="e.g. loading_dock" value={location}
              onChange={(e) => setLocation(e.target.value)}
              className={inputCls}
            />
          </Field>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="rounded bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {loading ? "Ingesting… (analyzing each frame)" : "Ingest & analyze"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      {verdict && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-1.5 text-[10px] font-bold uppercase ${severityClasses(verdict.severity)}`}
            >
              {verdict.alert ? `ALERT · ${verdict.severity}` : "no alert"}
            </span>
            <span className="text-sm font-semibold text-slate-100">{verdict.action_summary}</span>
            <span className="ml-auto text-xs text-slate-500">{result.frame_count} frames</span>
          </div>
          <p className="mt-2 text-sm text-slate-300">{verdict.narrative}</p>

          <div className="mt-3 flex gap-2 overflow-x-auto">
            {(result.frames || []).map((f, i) => (
              <img
                key={f.frame_id}
                src={f.blob_url}
                alt={f.object_type}
                title={`#${i} ${f.time} · ${f.object_type} · ${f.action}`}
                className={`h-16 w-24 flex-none rounded object-cover ${
                  i === verdict.key_frame_index ? "ring-2 ring-sky-400" : "border border-slate-800"
                }`}
              />
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

const inputCls =
  "w-full rounded bg-slate-800 px-2 py-1 text-sm text-slate-100 outline-none ring-slate-700 focus:ring-2";

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-0.5 block text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      {children}
    </label>
  );
}
