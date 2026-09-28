import type { Patient } from "../services/api";

export function PatientBanner({
  patient,
  recordCount,
  conflictCount,
  memoryCount,
  memoryAvailable,
}: {
  patient: Patient | null;
  recordCount: number;
  conflictCount: number;
  memoryCount: number | null;
  memoryAvailable: boolean;
}) {
  if (!patient) return null;

  return (
    <div className="patient-banner">
      <div className="patient-banner-main">
        <div className="avatar">
          {patient.name.split(" ").map((p) => p[0]).join("").toUpperCase()}
        </div>
        <div className="patient-banner-id">
          <h1>{patient.name}</h1>
          <div className="patient-banner-meta">
            {patient.age} years · {patient.sex} · {patient.blood_type}
            <span className="badge amber">Synthetic demo patient</span>
          </div>
        </div>
      </div>

      <div className="patient-banner-facts">
        <div className="banner-fact">
          <div className="banner-fact-label">Current concern</div>
          <div className="banner-fact-value">{patient.current_issue || "—"}</div>
        </div>
        <div className="banner-fact">
          <div className="banner-fact-label">Current medications</div>
          <div className="banner-fact-value">
            {patient.current_medications.length
              ? patient.current_medications.join(" · ")
              : "—"}
          </div>
        </div>
      </div>

      <div className="patient-banner-stats">
        <div className="stat">
          <span className="stat-num">{recordCount}</span>
          <span className="stat-label">records</span>
        </div>
        <div className="stat">
          <span className="stat-num warn">
            {conflictCount > 0 ? `⚠ ${conflictCount}` : "0"}
          </span>
          <span className="stat-label">potential conflicts</span>
        </div>
        <div className="stat">
          <span className="stat-num teal">
            {memoryAvailable ? (memoryCount ?? 0) : "—"}
          </span>
          <span className="stat-label">Hindsight memories</span>
        </div>
      </div>
    </div>
  );
}
