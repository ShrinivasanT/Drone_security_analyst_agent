import { useEffect, useState } from "react";
import { ingestImage, severityClasses, WAYPOINTS } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// Upload an image (or preview a video) and run the per-frame agent on it. Telemetry is
// chosen from a fixed waypoint dropdown plus editable time / altitude fields. Only images
// are ingested — a selected video is previewed but ingestion is blocked (see ARCH note in
// backend/routes/ingest.py: alerting is per-frame, the clip pipeline was removed).
export default function UploadPanel({ onIngested }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [isVideo, setIsVideo] = useState(false);

  const [location, setLocation] = useState(WAYPOINTS[0].location);
  const [time, setTime] = useState("22:30");
  const [altitude, setAltitude] = useState(20);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  // Revoke the object URL whenever it changes / on unmount to avoid leaking blobs.
  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl]);

  const onPick = (e) => {
    const f = e.target.files?.[0] || null;
    setError(null);
    setResult(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (!f) {
      setFile(null);
      setPreviewUrl(null);
      setIsVideo(false);
      return;
    }
    setFile(f);
    setIsVideo(f.type.startsWith("video/"));
    setPreviewUrl(URL.createObjectURL(f));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Choose an image first.");
      return;
    }
    if (isVideo) {
      setError("Video ingestion isn't supported — only images are ingested.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const wp = WAYPOINTS.find((w) => w.location === location);
      const fd = new FormData();
      fd.append("file", file);
      fd.append("location", location);
      if (time) fd.append("time", time);
      if (altitude !== "" && altitude != null) fd.append("altitude", String(altitude));
      if (wp) {
        fd.append("lat", String(wp.lat));
        fd.append("lng", String(wp.lng));
      }
      const data = await ingestImage(fd);
      setResult(data);
      onIngested?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const decision = result?.decision;

  return (
    <Panel title="Ingest Frame" subtitle="image → agent">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="flex-1 space-y-3">
          <input
            type="file"
            accept="image/*,video/*"
            onChange={onPick}
            className="block w-full text-sm text-slate-300 file:mr-3 file:rounded file:border-0 file:bg-sky-600 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-sky-500"
          />

          {isVideo && (
            <p className="rounded bg-amber-500/10 px-2 py-1.5 text-xs text-amber-300">
              Video selected — only images are ingested. Pick an image to analyze.
            </p>
          )}

          <div className="grid grid-cols-3 gap-2">
            <Field label="Location">
              <select
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className={inputCls}
              >
                {WAYPOINTS.map((w) => (
                  <option key={w.location} value={w.location}>
                    {w.location}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Time (HH:MM)">
              <input
                type="text"
                placeholder="22:30"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="Altitude (m)">
              <input
                type="number"
                min="0"
                step="0.5"
                value={altitude}
                onChange={(e) => setAltitude(e.target.value)}
                className={inputCls}
              />
            </Field>
          </div>

          <button
            type="submit"
            disabled={loading || isVideo || !file}
            className="rounded bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? "Ingesting…" : "Ingest & analyze"}
          </button>

          {error && <p className="text-sm text-red-400">{error}</p>}
        </div>

        {previewUrl && (
          <div className="sm:w-48">
            {isVideo ? (
              <video src={previewUrl} controls className="w-full rounded border border-slate-800" />
            ) : (
              <img src={previewUrl} alt="" className="w-full rounded border border-slate-800 object-cover" />
            )}
          </div>
        )}
      </form>

      {decision && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-800/40 p-3">
          <div className="flex items-center gap-2">
            <span
              className={`rounded px-1.5 text-[10px] font-bold uppercase ${severityClasses(decision.severity)}`}
            >
              {decision.route === "alert"
                ? `ALERT · ${decision.severity}`
                : decision.route === "log"
                ? "logged"
                : "no event"}
            </span>
            <span className="truncate text-sm font-semibold text-slate-100">
              {result.vlm?.object_type || "frame"}
            </span>
            <span className="ml-auto text-xs text-slate-500">
              {result.alerts_triggered} alert{result.alerts_triggered === 1 ? "" : "s"}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-300">{decision.summary}</p>
          {result.blob_url && (
            <img
              src={result.blob_url}
              alt=""
              className="mt-3 h-24 rounded border border-slate-800 object-cover"
            />
          )}
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
