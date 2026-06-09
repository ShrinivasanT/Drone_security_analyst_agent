import { useState } from "react";
import { postChat } from "../api.js";
import { Panel } from "./TelemetryFeed.jsx";

// Natural-language Q&A over the frame index. Each answer shows referenced frame thumbnails.
export default function ChatBox() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState([]);
  const [loading, setLoading] = useState(false);

  const ask = async (e) => {
    e?.preventDefault();
    const qq = question.trim();
    if (!qq) return;
    setQuestion("");
    setLoading(true);
    const currentTurns = [...turns, { role: "user", text: qq }];
    setTurns(currentTurns);
    // Build history from all prior turns (exclude the question we just added).
    const history = turns.map((t) => ({ role: t.role, content: t.text }));
    try {
      const data = await postChat(qq, history);
      setTurns((t) => [...t, { role: "assistant", text: data.answer, refs: data.references || [] }]);
    } catch (err) {
      setTurns((t) => [...t, { role: "assistant", text: `Error: ${err.message}`, refs: [] }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel title="Q&A Chatbox" subtitle="POST /chat">
      <div className="mb-3 space-y-3">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : ""}>
            <div
              className={`inline-block max-w-[90%] rounded-lg px-3 py-2 text-sm ${
                t.role === "user" ? "bg-sky-700 text-white" : "bg-slate-800 text-slate-200"
              }`}
            >
              {t.text}
            </div>
            {t.refs && t.refs.length > 0 && (
              <div className="mt-1 flex gap-1 overflow-x-auto">
                {t.refs.slice(0, 6).map((r) => (
                  <a key={r.frame_id} href={r.blob_url} target="_blank" rel="noreferrer" className="flex-none">
                    <img src={r.blob_url} alt={r.object_type} className="h-12 w-16 rounded object-cover" />
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && <p className="text-xs text-slate-500">thinking…</p>}
        {turns.length === 0 && (
          <p className="text-sm text-slate-500">
            Ask about the footage, e.g. “Were there any people after hours?”
          </p>
        )}
      </div>

      <form onSubmit={ask} className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded bg-slate-800 px-3 py-1.5 text-sm text-slate-100 outline-none ring-slate-700 focus:ring-2"
        />
        <button type="submit" className="rounded bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500">
          Ask
        </button>
      </form>
    </Panel>
  );
}
