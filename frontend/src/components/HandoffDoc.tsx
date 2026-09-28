import { useEffect, useState } from "react";
import { api } from "../services/api";
import { FadeIn } from "./Motion";

const SECTION_TITLES: Record<string, string> = {
  "CURRENT CONTEXT": "Current concern",
  "RECENT HISTORY": "Recent events",
  "RELEVANT MEDICATION CHANGES": "Medication changes",
  "PRIOR RELATED EVENTS": "Relevant history",
  "POTENTIAL CONFLICTS": "Potential conflicts",
  "VERIFICATION NEEDED": "What to verify",
  "LONGITUDINAL SYNTHESIS (from memory)": "Longitudinal synthesis — from Hindsight memory",
};

/** Clinician handoff, presented as a professional document (not chat output). */
export function HandoffDoc({ patientId, onBack }: { patientId: string; onBack: () => void }) {
  const [handoff, setHandoff] = useState<{
    sections: Record<string, string>;
    records_reviewed: string[];
    safety_note: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!patientId) return;
    api.handoff(patientId)
      .then(setHandoff)
      .catch((err) => setError(err?.message ?? String(err)))
      .finally(() => setLoading(false));
  }, [patientId]);

  if (loading) {
    return (
      <div className="handoff-doc" aria-live="polite">
        <div className="retrieval-indicator">
          <span className="spinner" aria-hidden="true" /> Assembling handoff from long-term
          memory…
        </div>
      </div>
    );
  }
  if (error)
    return (
      <div className="answer-block error-note" role="alert">
        {error}
      </div>
    );
  if (!handoff) return null;

  return (
    <FadeIn className="handoff-doc">
      <div className="handoff-head">
        <div>
          <h2>Longitudinal handoff</h2>
          <div className="handoff-provenance">
            Generated from the patient's synthetic records and Hindsight long-term memory. Every item requires
            clinician verification.
          </div>
        </div>
        <button className="btn" onClick={onBack}>Back</button>
      </div>

      {Object.entries(handoff.sections).map(([name, body]) => (
        <section key={name} className="handoff-section">
          <h4>{SECTION_TITLES[name] ?? name.toLowerCase()}</h4>
          <pre>{body}</pre>
        </section>
      ))}

      <section className="handoff-section">
        <h4>Records reviewed</h4>
        <pre>{handoff.records_reviewed.join(" · ")}</pre>
      </section>

      <p className="safety-note">{handoff.safety_note}</p>
    </FadeIn>
  );
}
