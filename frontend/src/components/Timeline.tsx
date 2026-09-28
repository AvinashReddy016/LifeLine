import type { TimelineEvent } from "../services/api";

const KIND_LABEL: Record<string, string> = {
  medication: "Medication",
  emergency: "Emergency",
  symptom: "Symptom",
  lab: "Lab",
  visit: "Visit",
};

export function Timeline({ events, onOpenRecord }: { events: TimelineEvent[]; onOpenRecord: (recordId: string) => void }) {
  if (!events.length) return <p className="empty-note">No timeline events. Seed the demo patient first.</p>;
  return (
    <div className="timeline">
      {events.map((event) => (
        <div key={`${event.record_id}-${event.date}`} className={`tl-item kind-${event.kind}`}>
          <div className="tl-date">
            {event.date}
            {event.kind !== "visit" && ` · ${KIND_LABEL[event.kind] ?? event.kind}`}
          </div>
          <div className="tl-title">{event.title}</div>
          <div className="tl-detail">{event.detail}</div>
          {event.record_id && (
            <button className="tl-rid linkish" onClick={() => onOpenRecord(event.record_id)} style={{ background: "none", border: "none", padding: 0 }}>
              {event.record_id}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
