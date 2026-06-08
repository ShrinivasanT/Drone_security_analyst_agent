// Backend base URL. Baked at build time (VITE_API_BASE) or defaults to the host-
// published backend port. The browser also fetches frame images directly from MinIO
// via the absolute blob_url stored on each record (MINIO_PUBLIC_ENDPOINT).
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function postJSON(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const getEvents = (limit = 50) => getJSON(`/events?limit=${limit}`);
export const getAlerts = (activeOnly = true, limit = 50) =>
  getJSON(`/alerts?active_only=${activeOnly}&limit=${limit}`);
export const searchFrames = (q, limit = 12) =>
  getJSON(`/frames/search?q=${encodeURIComponent(q)}&limit=${limit}`);
export const getSummary = () => getJSON(`/summary`);
export const postChat = (question) => postJSON(`/chat`, { question });
export const getClips = (limit = 20) => getJSON(`/clips?limit=${limit}`);

// Upload + ingest a video clip (multipart). `formData` carries the file + telemetry
// fields; do NOT set Content-Type — the browser adds the multipart boundary itself.
async function ingestVideo(formData) {
  const res = await fetch(`${API_BASE}/ingest_video`, { method: "POST", body: formData });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}
export { ingestVideo };

// Severity → Tailwind classes for badges/borders.
export const severityClasses = (severity) =>
  ({
    critical: "bg-red-600 text-white",
    high: "bg-orange-500 text-white",
    warning: "bg-yellow-400 text-black",
    info: "bg-slate-600 text-white",
  }[severity] || "bg-slate-600 text-white");

export { API_BASE };
