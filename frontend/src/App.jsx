import AlertBanner from "./components/AlertBanner.jsx";
import TelemetryFeed from "./components/TelemetryFeed.jsx";
import EventLog from "./components/EventLog.jsx";
import FrameSearch from "./components/FrameSearch.jsx";
import ChatBox from "./components/ChatBox.jsx";
import SessionSummary from "./components/SessionSummary.jsx";
import VideoUpload from "./components/VideoUpload.jsx";
import { API_BASE } from "./api.js";

export default function App() {
  return (
    <div className="min-h-full bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-3">
        <div className="flex items-center justify-between">
          <h1 className="flex items-center gap-2 text-lg font-bold">
            <span>🛰️</span> Drone Security Analyst
          </h1>
          <span className="text-xs text-slate-500">api: {API_BASE}</span>
        </div>
      </header>

      <main className="space-y-4 p-4 lg:p-6">
        <AlertBanner />

        <VideoUpload />

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="h-[360px] lg:col-span-1">
            <TelemetryFeed />
          </div>
          <div className="h-[360px] lg:col-span-2">
            <FrameSearch />
          </div>

          <div className="h-[420px] lg:col-span-2">
            <EventLog />
          </div>
          <div className="flex h-[420px] flex-col gap-4">
            <div className="min-h-0 flex-1">
              <SessionSummary />
            </div>
          </div>

          <div className="h-[420px] lg:col-span-3">
            <ChatBox />
          </div>
        </div>
      </main>
    </div>
  );
}
