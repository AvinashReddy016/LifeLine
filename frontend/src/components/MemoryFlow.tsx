import { useEffect, useState } from "react";
import { api } from "../services/api";
import { Reveal } from "./Motion";

type Status = { available: boolean; bank_id?: string; memory_count?: number; sample?: string[]; reason?: string };

const FLOW: { key: string; title: string; blurb: string; tech: string }[] = [
  {
    key: "records",
    title: "Records",
    blurb: "The patient's fragmented documents — visits, labs, prescriptions, discharge summaries.",
    tech: "Stored in the local record store and loaded from seed/patients.json.",
  },
  {
    key: "retain",
    title: "Hindsight Retain",
    blurb: "Each record is broken into single, dated facts and written into the patient's own long-term memory.",
    tech: "record-to-memory decomposition, then hindsight.retain_batch() with provenance metadata (record_id, event_type, date).",
  },
  {
    key: "memory",
    title: "Long-term patient memory",
    blurb: "One isolated memory bank per patient — memories from one patient can never surface for another.",
    tech: "One bank per patient, strictly isolated server-side.",
  },
  {
    key: "recall",
    title: "Hindsight Recall",
    blurb: "Every question is probed from several angles — medications, changes over time, similar past events, contradictions.",
    tech: "Multi-dimension recall plan; each dimension runs a real recall call; results merged, ranked, de-duplicated.",
  },
  {
    key: "history",
    title: "Relevant history",
    blurb: "The recalled memories are linked back to their source records so every claim is traceable.",
    tech: "Provenance via metadata record ids → link to source records → evidence payloads.",
  },
  {
    key: "reflect",
    title: "Hindsight Reflect",
    blurb: "The memory system synthesizes the whole longitudinal story — used in the clinician handoff.",
    tech: "hindsight.reflect() over the patient's bank; falls back to deterministic sections if unavailable.",
  },
];

export function MemoryFlow({ patientId }: { patientId: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [showTech, setShowTech] = useState(false);

  useEffect(() => {
    if (!patientId) return;
    api.getMemoryStatus(patientId).then(setStatus).catch(() => setStatus({ available: false }));
  }, [patientId]);

  return (
    <div className="memory-flow">
      <h2 className="memory-flow-title">How LifeLine remembers</h2>

      <div className="memory-flow-status">
        {status === null ? (
          <span className="memory-chip">
            <span className="memory-dot" aria-hidden="true" /> Checking Hindsight memory…
          </span>
        ) : status.available ? (
          <span className="memory-chip live">
            <span className="memory-dot live" aria-hidden="true" /> Hindsight live ·{" "}
            {status.memory_count ?? 0} memories in this patient's bank
          </span>
        ) : (
          <span className="memory-chip">
            <span className="memory-dot" aria-hidden="true" /> Hindsight offline
            {status.reason ? ` · ${status.reason}` : ""}
          </span>
        )}
      </div>

      <div className="flow-vertical">
        {FLOW.map((step, i) => (
          <Reveal key={step.key} delay={Math.min(i, 5) * 0.05}>
            <div className="flow-node">
              <div className="flow-node-card">
                <div className="flow-node-step">{i + 1}</div>
                <div>
                  <div className="flow-node-title">{step.title}</div>
                  <div className="flow-node-blurb">{step.blurb}</div>
                  {showTech && <div className="flow-node-tech">{step.tech}</div>}
                </div>
              </div>
              {i < FLOW.length - 1 && (
                <div className="flow-arrow-down" aria-hidden="true">
                  ↓
                </div>
              )}
            </div>
          </Reveal>
        ))}
      </div>

      <button
        className="memory-flow-tech-toggle"
        onClick={() => setShowTech((v) => !v)}
        type="button"
      >
        {showTech ? "Hide technical details" : "Show technical details"}
      </button>

      {status?.available && (status.sample?.length ?? 0) > 0 && (
        <div className="memory-sample">
          <h3 className="answer-heading">Inside this patient's memory bank</h3>
          {status.sample!.map((text, i) => (
            <div key={i} className="memory-sample-row">{text}</div>
          ))}
        </div>
      )}
    </div>
  );
}
