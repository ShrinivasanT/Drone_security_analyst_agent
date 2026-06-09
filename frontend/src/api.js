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

// Fixed patrol waypoints (mirrors data/video_loader.py _WAYPOINTS). Drives the telemetry
// dropdown so an uploaded image is tagged with a plausible location + coordinates.
export const WAYPOINTS = [
  { location: "main_gate", lat: 18.5204, lng: 73.8567 },
  { location: "parking_lot", lat: 18.521, lng: 73.857 },
  { location: "warehouse_a", lat: 18.5215, lng: 73.8575 },
  { location: "perimeter_north", lat: 18.522, lng: 73.858 },
  { location: "perimeter_east", lat: 18.5218, lng: 73.859 },
  { location: "loading_dock", lat: 18.5212, lng: 73.8585 },
];

// Multipart upload of a single image + telemetry → runs the per-frame agent.
export async function ingestImage(formData) {
  const res = await fetch(`${API_BASE}/ingest_image`, { method: "POST", body: formData });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`/ingest_image -> ${detail}`);
  }
  return res.json();
}

export const getEvents = (limit = 50) => getJSON(`/events?limit=${limit}`);
export const getFrames = (limit = 10) => getJSON(`/frames?limit=${limit}`);
export const getAlerts = (activeOnly = true, limit = 50) =>
  getJSON(`/alerts?active_only=${activeOnly}&limit=${limit}`);
export const searchFrames = (q, limit = 12) =>
  getJSON(`/frames/search?q=${encodeURIComponent(q)}&limit=${limit}`);
export const getSummary = () => getJSON(`/summary`);
export const postChat = (question, history = []) => postJSON(`/chat`, { question, history });

// Severity → Tailwind classes for badges/borders.
export const severityClasses = (severity) =>
  ({
    critical: "bg-red-600 text-white",
    high: "bg-orange-500 text-white",
    warning: "bg-yellow-400 text-black",
    info: "bg-slate-600 text-white",
  }[severity] || "bg-slate-600 text-white");

export { API_BASE };
