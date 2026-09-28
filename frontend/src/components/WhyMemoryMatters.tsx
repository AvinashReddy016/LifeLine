import { useState } from "react";
import { api } from "../services/api";
import { FadeIn } from "./Motion";

const QUESTION = "What changed since the last hospital visit?";

type DemoResult = {
  question: string;
  without_memory: { answer: string; memories_used: number; source_records_linked: number; conflicts_surfaced: unknown[] };
  with_memory: { answer: string; memories_used: number; source_records_linked: number; conflicts_surfaced: unknown[] };
};

/**
 * "Why memory matters": the same question answered with and without long-term
 * memory, side by side, using real backend data (no mock differences).
 */
export function WhyMemoryMatters({ patientId }: { patientId: string }) {
  const [result, setResult] = useState<DemoResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    if (!patientId) return;
    setLoading(true);
    setError("");
    try {
      setResult((await api.demoMode(QUESTION, patientId)) as DemoResult);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="why-memory">
      <h2 className="memory-flow-title">Why memory matters</h2>
      <p className="why-memory-sub">
        The same question — “{QUESTION}” — answered two ways, live against this patient's records.
      </p>

      <button className="btn primary why-memory-run" onClick={run} type="button" disabled={loading || !patientId}>
        {loading ? "Running both modes…" : "Run the comparison"}
      </button>

      {loading && (
        <div className="retrieval-indicator">
          <span className="spinner" aria-hidden="true" /> Recalling with and without memory…
        </div>
      )}
      {error && (
        <div className="answer-block error-note" role="alert">
          {error}
        </div>
      )}

      {result && (
        <FadeIn className="compare-grid">
          <div className="compare-col without">
            <h4>Without long-term memory</h4>
            <div className="compare-tags">
              <span className="badge gray">limited current context</span>
              <span className="badge gray">{result.without_memory.memories_used} relevant memories</span>
              <span className="badge gray">{result.without_memory.source_records_linked} records linked</span>
            </div>
            <div className="compare-answer">{result.without_memory.answer}</div>
          </div>

          <div className="compare-col with">
            <h4>With Hindsight memory</h4>
            <div className="compare-tags">
              <span className="badge teal">longitudinal context</span>
              <span className="badge teal">{result.with_memory.memories_used} relevant memories</span>
              <span className="badge teal">{result.with_memory.source_records_linked} records linked</span>
              {result.with_memory.conflicts_surfaced.length > 0 && (
                <span className="badge amber">{result.with_memory.conflicts_surfaced.length} conflicts surfaced</span>
              )}
            </div>
            <div className="compare-answer">{result.with_memory.answer}</div>
          </div>
        </FadeIn>
      )}
    </div>
  );
}
