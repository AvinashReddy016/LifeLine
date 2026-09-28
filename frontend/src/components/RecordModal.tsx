import { useEffect, useRef, useState } from "react";
import { api, type Record_ } from "../services/api";

export function RecordModal({
  recordId,
  patientId,
  onClose,
}: {
  recordId: string;
  patientId?: string;
  onClose: () => void;
}) {
  const [record, setRecord] = useState<Record_ | null>(null);
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Fetch the record's owning patient's records; fall back to the store's first patient.
    const resolvePatient = async (): Promise<string> => {
      if (patientId) return patientId;
      const res = await api.getPatients();
      const patients = [...res.patients].sort((a, b) => a.patient_id.localeCompare(b.patient_id));
      if (!patients.length) throw new Error("No patients found. POST /api/demo/seed first.");
      return patients[0].patient_id;
    };

    let cancelled = false;
    resolvePatient()
      .then((pid) => api.getRecords(pid))
      .then((res) => {
        if (cancelled) return;
        const found = res.records.find((r) => r.record_id === recordId);
        if (found) setRecord(found);
        else setError(`Record ${recordId} not found`);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err.message ?? err));
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, patientId]);

  // Move focus into the dialog and allow Escape to dismiss it.
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Source record"
        onClick={(e) => e.stopPropagation()}
      >
        <button ref={closeRef} type="button" className="btn modal-close" onClick={onClose}>
          Close
        </button>

        {!record && <p className="empty-note">{error || "Loading record…"}</p>}

        {record && (
          <>
            <span className="badge teal">{record.record_type.replace(/_/g, " ")}</span>
            <h3>{record.title}</h3>
            <div className="modal-sub">
              {record.record_id} · {record.date} · {record.facility} · {record.clinician}
            </div>
            <p className="modal-summary">{record.summary}</p>
            <div className="modal-body">{record.body}</div>
          </>
        )}
      </div>
    </div>
  );
}
