import { useState } from "react";
import { api, type ChatResponse } from "../services/api";
import { FadeIn } from "./Motion";
import { Markdown } from "./Markdown";

const SUGGESTED_QUESTIONS = [
  "What changed since the last hospital visit?",
  "Have similar symptoms appeared before?",
  "What happened after the medication change?",
  "Are there conflicting records?",
  "What information is uncertain?",
  "What should a clinician verify?",
];

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

type Memory = ChatResponse["memories_used"][number];

interface MemoryCardProps {
  memory: Memory;
  onOpenRecord: (id: string) => void;
}

function MemoryCard({ memory, onOpenRecord }: MemoryCardProps) {
  const [showTech, setShowTech] = useState(false);

  const rid = memory.record_ids[0];
  const template = DIMENSION_TEMPLATES[memory.dimension] ?? "Recalled from the patient's long-term memory.";
  const why = `${template} Score: ${Math.round((memory.score ?? 0) * 100)}%.`;

  return (
    <div className="memory-card">
      <div className="memory-card-head">
        {rid && (
          <button type="button" className="memory-card-rid" onClick={() => onOpenRecord(rid)}>
            {rid}
          </button>
        )}
        {memory.date && <span className="memory-card-date">{memory.date}</span>}
      </div>
      <div className="memory-card-text">{memory.text}</div>
      <div className="memory-card-why">{why}</div>
      <button
        className="memory-card-tech-toggle"
        onClick={() => setShowTech((v) => !v)}
        type="button"
      >
        {showTech ? "Hide technical details" : "Technical details"}
      </button>
      {showTech && (
        <div className="memory-card-tech">
          <div>relevance: {Math.round((memory.score ?? 0) * 100)}%</div>
          <div>dimension: {memory.dimension || "direct"}</div>
          <div>memory type: {memory.memory_type || "experience"}</div>
          <div>date: {memory.date || "—"}</div>
          <div>records: {memory.record_ids.join(", ") || "—"}</div>
        </div>
      )}
    </div>
  );
}

/**
 * Splits the real LLM answer into a short prose summary and the structured
 * remainder (tables / lists / headings), so the UI can show "Summary" first
 * and "Key findings" below it. Nothing is invented — both parts are the
 * backend's own text, only the presentation point is chosen here.
 */
function splitSummaryAndFindings(answer: string): { summary: string; findings: string } {
  const lines = answer.replace(/\r\n/g, "\n").split("\n");
  const isStructuredBlockStart = (line: string) => {
    const t = line.trim();
    if (!t) return false;
    return t.startsWith("|") || t.startsWith("#") || /^([-*+]|\d+[.)])\s/.test(t);
  };
  const cut = lines.findIndex(isStructuredBlockStart);
  if (cut < 0) return { summary: answer.trim(), findings: "" };
  const summary = lines.slice(0, cut).join("\n").trim();
  const findings = lines.slice(cut).join("\n").trim();
  return { summary, findings };
}

export function AskLifeLine({ patientId, onOpenRecord }: { patientId: string; onOpenRecord: (id: string) => void }) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showAllMemories, setShowAllMemories] = useState(false);
  const [showVerification, setShowVerification] = useState(true);

  async function ask(q: string) {
    if (!q.trim() || loading || !patientId) return;
    setLoading(true);
    setError("");
    setAsked(q);
    setShowAllMemories(false);
    setShowVerification(true);
    try {
      setAnswer(await api.chat(patientId, q));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
      setQuestion("");
    }
  }

  const memories = showAllMemories ? (answer?.memories_used ?? []) : ((answer?.memories_used ?? [])).slice(0, 3);
  const hasEvidence = (answer?.memories_used.length ?? 0) > 0;
  const hasConflicts = (answer?.conflicts.length ?? 0) > 0;
  const hasUncertainty = (answer?.uncertainty.length ?? 0) > 0;
  // Honest zero-evidence state: Hindsight recalled nothing for this question.
  const noHistoricalRecords = !!answer && !hasEvidence;

  const { summary, findings } = answer
    ? splitSummaryAndFindings(answer.answer)
    : { summary: "", findings: "" };

  // "Why this matters" — computed from the actual retrieved evidence only.
  const dates = (answer?.memories_used ?? []).map((m) => m.date).filter(Boolean).sort();
  const span =
    dates.length && dates[0].slice(0, 4) === dates[dates.length - 1].slice(0, 4)
      ? dates[0].slice(0, 4)
      : dates.length
      ? `${dates[0].slice(0, 4)}–${dates[dates.length - 1].slice(0, 4)}`
      : null;
  const sourceCount = new Set((answer?.source_records ?? []).map((s) => s.record_id)).size;

  return (
    <div className="ask-lifeline">
      <div className="ask-lifeline-head">
        <h2 className="ask-lifeline-title">Ask LifeLine</h2>
        <p className="ask-lifeline-sub">Ask about the patient&apos;s history.</p>
      </div>

      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
      >
        <label className="ask-label" htmlFor="ask-input">
          What would you like to know about this patient&apos;s history?
        </label>
        <div className="ask-row">
          <input
            id="ask-input"
            className="ask-input"
            placeholder="e.g. What changed since the last hospital visit?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button className="btn primary ask-btn" type="submit" disabled={loading || !question.trim()}>
            {loading ? "Recalling…" : "Ask LifeLine"}
          </button>
        </div>
        <div className="ask-suggestions">
          {SUGGESTED_QUESTIONS.map((s) => (
            <button key={s} type="button" className="suggestion-chip" disabled={loading} onClick={() => ask(s)}>
              {s}
            </button>
          ))}
        </div>
      </form>

      {loading && (
        <div className="answer-block" aria-live="polite">
          <div className="retrieval-indicator">
            <span className="spinner" aria-hidden="true" /> Retrieving relevant history from
            long-term memory…
          </div>
        </div>
      )}

      {error && !loading && <div className="answer-block error-note">⚠ {error}</div>}

      {asked && !loading && !answer && !error && (
        <div className="empty-note">Ask a question to reconstruct this patient&apos;s longitudinal story.</div>
      )}

      {answer && !loading && (
        <FadeIn className="answer-stack">
          <div className="asked-line">“{asked}”</div>

          {/* ------------------------------------------------ answer first */}
          <section className="answer-block">
            <h3 className="answer-heading">LifeLine answer</h3>

            {noHistoricalRecords && (
              <div className="no-records-banner" role="status">
                <div className="no-records-title">No historical records found</div>
                <p className="no-records-text">
                  LifeLine could not find relevant historical records for this question.
                </p>
                <p className="no-records-text">
                  Because no relevant historical records were recalled, LifeLine cannot provide a
                  historical comparison.
                </p>
              </div>
            )}

            {summary && (
              <div className="answer-summary">
                <Markdown>{summary}</Markdown>
              </div>
            )}

            {/* Structured findings (tables, lists) from the real answer.
                With evidence they are historical findings; without evidence
                they are clearly framed as clinician verification items, never
                as recalled history. */}
            {findings && (
              <div className="answer-findings">
                <div className="answer-subheading">{hasEvidence ? "Key findings & changes" : "Items to verify"}</div>
                <Markdown>{findings}</Markdown>
              </div>
            )}

            {hasEvidence && (
              <div className="why-matters">
                <h4 className="answer-heading">Why this matters</h4>
                <p>
                  LifeLine assembled this from {answer.memories_used.length} historical
                  memories recalled from long-term memory{span ? ` spanning ${span}` : ""}, each
                  linked to its source record {sourceCount > 0 ? `(${sourceCount} record${sourceCount === 1 ? "" : "s"} attached below)` : ""}.
                  {hasConflicts && (
                    <>
                      {" "}
                      {answer.conflicts.length} potential conflict{answer.conflicts.length === 1 ? "" : "s"} surfaced — never
                      auto-resolved.
                    </>
                  )}
                </p>
              </div>
            )}
          </section>

          {/* --------------------------------------------- items to verify */}
          {(hasConflicts || hasUncertainty) && (
            <section className="verification-block">
              <button className="verification-head" onClick={() => setShowVerification((v) => !v)} type="button">
                <span className="verification-title">
                  ⚠ Verification needed
                  {hasConflicts && <span className="conflict-badge">Potential conflict — clinician verification required</span>}
                </span>
                <span className="verification-count">
                  {answer.conflicts.length} conflict{answer.conflicts.length === 1 ? "" : "s"}
                  {answer.uncertainty.length ? ` · ${answer.uncertainty.length} note${answer.uncertainty.length === 1 ? "" : "s"}` : ""}
                </span>
              </button>
              {showVerification && (
                <div className="verification-body">
                  {answer.uncertainty.map((note, i) => (
                    <div key={i} className="verification-item">{note}</div>
                  ))}
                  {answer.conflicts.map((c) => (
                    <div key={c.conflict_id} className="verification-item conflict">
                      <div className="verification-type">{c.type.replace(/_/g, " ")}</div>
                      <p>{c.description}</p>
                      <div className="verification-claims">
                        <div>
                          <button
                            type="button"
                            className="rid"
                            onClick={() => onOpenRecord(c.record_a_id)}
                          >
                            {c.record_a_id} · {c.record_a_date}
                          </button>
                          “{c.record_a_claim}”
                        </div>
                        <div>
                          <button
                            type="button"
                            className="rid"
                            onClick={() => onOpenRecord(c.record_b_id)}
                          >
                            {c.record_b_id} · {c.record_b_date}
                          </button>
                          “{c.record_b_claim}”
                        </div>
                      </div>
                      <div className="verification-status">Status: UNRESOLVED — needs clinician verification.</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* ------------------------------------------ hindsight evidence */}
          <section className="memory-evidence">
            <button
              className="memory-evidence-head"
              onClick={() => setShowAllMemories((v) => !v)}
              type="button"
              disabled={!hasEvidence}
            >
              <span>Why this answer — Hindsight evidence</span>
              <span className="memory-evidence-count">
                {hasEvidence
                  ? `${answer.memories_used.length} relevant memor${answer.memories_used.length === 1 ? "y" : "ies"} used${
                      answer.memories_used.length > 3 ? (showAllMemories ? " · show less" : " · show all") : ""
                    }`
                  : "no historical evidence found"}
              </span>
            </button>
            {!hasEvidence && (
              <div className="memory-empty">
                No historical evidence was recalled for this question — the answer above is not
                based on historical records.
              </div>
            )}
            <div className="memory-card-list">
              {memories.map((m) => (
                <MemoryCard key={m.id} memory={m} onOpenRecord={onOpenRecord} />
              ))}
            </div>
          </section>

          {/* ------------------------------------------------ source records */}
          <section className="source-records">
            <h3 className="answer-heading">Source records</h3>
            {answer.source_records.length === 0 && <div className="empty-note">No source records were found.</div>}
            <div className="source-record-list">
              {answer.source_records.map((r) => (
                <button key={r.record_id} className="source-record" onClick={() => onOpenRecord(r.record_id)} type="button">
                  <span className="source-record-rid">{r.record_id}</span>
                  <span className="source-record-title">{r.title}</span>
                  <span className="source-record-date">{r.date}</span>
                </button>
              ))}
            </div>
          </section>

          <div className="safety-note">{answer.safety_note}</div>
        </FadeIn>
      )}
    </div>
  );
}
