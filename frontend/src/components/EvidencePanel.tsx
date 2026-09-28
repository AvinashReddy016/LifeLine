import { useState } from "react";
import type { ChatResponse } from "../services/api";

function answerPlural(n: number): string {
  return n === 1 ? "y" : "ies";
}

export function EvidencePanel({
  data,
  onOpenRecord,
}: {
  data: ChatResponse;
  onOpenRecord: (recordId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const memories = expanded ? data.memories_used : data.memories_used.slice(0, 4);

  return (
    <div className="memory-evidence">
      <button
        className="memory-evidence-head"
        onClick={() => setExpanded((v) => !v)}
        type="button"
        disabled={data.memories_used.length === 0}
      >
        <span>🧠 Hindsight memory</span>
        <span className="memory-evidence-count">
          {data.memories_used.length} relevant memoria{answerPlural(data.memories_used.length)} used
          {data.memories_used.length > 3 ? (expanded ? " · show less" : " · show all") : ""}
        </span>
      </button>

      {data.memories_used.length === 0 && (
        <div className="memory-empty">No historical memories matched this question. The answer says so honestly.</div>
      )}

      <div className="memory-card-list">
        {memories.map((memory) => (
          <div key={memory.id} className="memory-card">
            <div className="memory-card-head">
              {memory.record_ids[0] && (
                <span className="memory-card-rid" onClick={() => onOpenRecord(memory.record_ids[0])}>
                  {memory.record_ids[0]}
                </span>
              )}
              {memory.date && <span className="memory-card-date">{memory.date}</span>}
            </div>
            <div className="memory-card-text">{memory.text}</div>
            <div className="memory-card-why">
              {DIMENSION_TEMPLATES[memory.dimension] ?? "Recalled from the patient's long-term memory."}
            </div>
            <button
              className="memory-card-tech-toggle"
              onClick={() => setExpanded((v) => !v)}
              type="button"
            >
              {expanded ? "Hide technical details" : "Technical details"}
            </button>
            {expanded && (
              <div className="memory-card-tech">
                <div>relevance: {Math.round((memory.score ?? 0) * 100)}%</div>
                <div>dimension: {memory.dimension || "direct"}</div>
                <div>memory type: {memory.memory_type || "experience"}</div>
                <div>date: {memory.date || "—"}</div>
                <div>records: {memory.record_ids.join(", ") || "—"}</div>
              </div>
            )}
          </div>
        ))}
      </div>

      {data.memories_used.length > 4 && (
        <button className="btn" style={{ margin: "10px 16px", fontSize: 12.5, padding: "7px 12px" }} type="button">
          {expanded ? "Show less" : `Show all ${data.memories_used.length} memories`}
        </button>
      )}

      {data.conflicts.length > 0 && (
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
          {data.conflicts.map((conflict) => (
            <div key={conflict.conflict_id} style={{ background: "var(--card)", border: "1px solid #f0d9c0", borderRadius: "var(--radius-sm)", padding: "14px 16px" }}>
              <div style={{ fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--amber)", marginBottom: 6 }}>
                ⚠ Potential conflict — {conflict.type.replace(/_/g, " ")}
              </div>
              <p>{conflict.description}</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
                <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "var(--teal)", marginBottom: 4 }}>
                  {conflict.record_a_id} · {conflict.record_a_date}
                </div>
                <div style={{ fontFamily: "ui-monospace, monospace", fontSize: 11, color: "var(--teal)", marginBottom: 4 }}>
                  {conflict.record_b_id} · {conflict.record_b_date}
                </div>
                <div>“{conflict.record_a_claim}”</div>
                <div>“{conflict.record_b_claim}”</div>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--amber)", marginTop: 8 }}>
                Status: UNRESOLVED — needs clinician verification.
              </div>
            </div>
          ))}
        </div>
      )}

      {data.uncertainty.length > 0 && (
        <div style={{ padding: "10px 16px", borderTop: "1px solid var(--line)", fontSize: 12.5, color: "var(--amber)", background: "var(--amber-soft)" }}>
          {data.uncertainty.map((note, i) => (
            <div key={i} style={{ marginBottom: 6 }}>⚠ {note}</div>
          ))}
        </div>
      )}

      <div className="safety-note">{data.safety_note}</div>
    </div>
  );
}

const DIMENSION_TEMPLATES: Record<string, string> = {
  direct: "Matched your exact question in long-term memory.",
  medication_history: "Found while looking across the patient's medication records.",
  recent_changes: "Matched while tracing what changed over time.",
  similar_events: "Found while searching for earlier similar events.",
  conflicts: "Recalled while checking for contradicting entries.",
  interactions: "Recalled from an earlier LifeLine session with this patient.",
  emergencies: "Found while scanning emergency and urgent-care history.",
  handoff: "Part of the most clinically relevant history for this situation.",
};
