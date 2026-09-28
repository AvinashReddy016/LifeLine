import { useState } from "react";
import { api, type ChatResponse } from "../services/api";
import { EvidencePanel } from "./EvidencePanel";

const SUGGESTIONS = [
  "What should I tell the doctor?",
  "What changed since the last hospital visit?",
  "Have similar symptoms appeared before?",
  "What medications were started recently?",
  "What was documented during the last emergency visit?",
  "Are there conflicting entries in the patient's history?",
  "Summarize the patient's recent history for a handoff.",
  "Why did you surface these records?",
];

export function ChatPanel({ patientId, onOpenRecord }: { patientId: string; onOpenRecord: (id: string) => void }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [asked, setAsked] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask(q: string) {
    if (!q.trim() || loading) return;
    setLoading(true);
    setError("");
    setAsked(q);
    try {
      const response = await api.chat(patientId, q);
      setAnswer(response);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
      setQuestion("");
    }
  }

  return (
    <div className="chat-panel">
      <div className="ask-form" style={{ padding: "20px 22px" }}>
        <label className="ask-label" htmlFor="chat-ask">
          Ask LifeLine
        </label>
        <div className="ask-row" style={{ marginTop: 8 }}>
          <input
            id="chat-ask"
            className="ask-input"
            placeholder="What would you like to know about this patient's history?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn primary" style={{ padding: "11px 20px" }} type="submit" disabled={loading || !question.trim()}>
            {loading ? "Recalling…" : "Ask"}
          </button>
        </div>
        <div className="suggestions" style={{ marginTop: 12 }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="suggestion-chip" disabled={loading} type="button">
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="chat-scroll">
        {asked && <div className="msg-user">{asked}</div>}

        {loading && (
          <div className="msg-agent">
            <div className="msg-answer" style={{ color: "var(--ink-faint)" }}>
              Recalling relevant history from long-term memory…
            </div>
          </div>
        )}

        {error && !loading && (
          <div className="msg-agent">
            <div className="msg-answer" style={{ borderColor: "#f0c9c9", background: "var(--red-soft)" }}>
              {error}
            </div>
          </div>
        )}

        {answer && !loading && (
          <div className="msg-agent">
            <div className="msg-answer">{answer.answer}</div>
            <EvidencePanel data={answer} onOpenRecord={onOpenRecord} />
          </div>
        )}

        {!asked && !loading && (
          <div className="card" style={{ textAlign: "center", padding: "32px 20px" }}>
            <h3 style={{ marginBottom: 8 }}>Ask about the patient's longitudinal history</h3>
            <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.6, maxWidth: 440, margin: "0 auto" }}>
              Every answer is reconstructed from memories stored in Hindsight and linked back to
              source records. Potential conflicts are surfaced, never silently resolved.
            </p>
          </div>
        )}
      </div>

      <form
        className="chat-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <input
          className="chat-input"
          placeholder="Ask about medications, changes, prior events, conflicts…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="btn primary" type="submit" disabled={loading || !question.trim()}>
          {loading ? "Recalling…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
