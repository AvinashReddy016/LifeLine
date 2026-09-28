import { useState } from "react";
import { api, type JourneyStory } from "../services/api";
import { Reveal } from "./Motion";

/** MEMORY JOURNEY — "LifeLine becomes more useful because it remembers." */
export function MemoryJourney({ patientId }: { patientId: string }) {
  const [story, setStory] = useState<JourneyStory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!patientId) return;
    setLoading(true);
    setError("");
    try {
      setStory(await api.memoryJourney(patientId));
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
    }
  }

  const question = story?.question ?? "What is going on with this patient's dizziness and medications?";

  return (
    <div className="journey">
      <h2 className="memory-flow-title">Memory journey</h2>
      <p className="journey-sub">
        The same question — “{question}” — asked while LifeLine remembers progressively more of the
        patient's history. Live retain + recall, no staging.
      </p>

      <button className="btn primary journey-run" onClick={run} type="button" disabled={loading || !patientId}>
        {loading ? "Running the journey…" : "Run the memory journey"}
      </button>

      {loading && (
        <div className="retrieval-indicator">
          <span className="spinner" aria-hidden="true" /> Retaining and recalling at each stage…
        </div>
      )}
      {error && (
        <div className="answer-block error-note" role="alert">
          {error}
        </div>
      )}

      {story && (
        <>
          {story.error && <div className="uncertainty">{story.error}</div>}
          <div className="journey-track">
            {story.stages.map((stage, i) => (
              <Reveal key={stage.stage} delay={Math.min(i, 4) * 0.06} className="journey-stage">
                <div className="journey-marker">
                  <span className="journey-step">Interaction {stage.interactions}</span>
                  {stage.stage < story.stages.length && <span className="journey-arrow">↓</span>}
                </div>
                <div className={`journey-card ${stage.recall_available ? "" : "degraded"}`}>
                  <div className="journey-card-head">
                    <span className="badge gray">{stage.records_in_memory} records in memory</span>
                    <span className="badge teal">{stage.memories_recalled} memories recalled</span>
                    {stage.record_count > 0 && <span className="badge teal">{stage.record_count} records linked</span>}
                  </div>
                  {stage.preview.length > 0 ? (
                    <div className="journey-preview">
                      {stage.preview.slice(0, 2).map((text, i) => (
                        <div key={i} className="journey-preview-row">{text}…</div>
                      ))}
                    </div>
                  ) : (
                    <div className="journey-preview">
                      <div className="journey-preview-row muted">
                        {stage.error ? `Memory error: ${stage.error}` : "Nothing relevant in memory yet — the answer has almost no history to draw on."}
                      </div>
                    </div>
                  )}
                </div>
              </Reveal>
            ))}
          </div>
          <p className="journey-note">{story.note}</p>
        </>
      )}
    </div>
  );
}
