import { useState } from "react";
import { StaggerItem } from "./Motion";
import type { TimelineEvent } from "../services/api";

const KIND_LABEL: Record<string, string> = {
  medication: "Medication",
  emergency: "Emergency",
  symptom: "Symptom",
  lab: "Lab",
  visit: "Visit",
  conflict: "Conflict",
};

/**
 * Chronological patient story. Collapsed by default — one line per event.
 * Selecting an event expands its detail inline. The most recent event (today's
 * concern) is highlighted. The REC-ID is a plain label here: the row itself is
 * a button, so opening the source record happens from the expanded detail.
 */
export function PatientStory({
  events,
  onOpenRecord,
}: {
  events: TimelineEvent[];
  onOpenRecord: (recordId: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (!events.length) {
    return (
      <p className="empty-note">
        No story yet. Seed the demo patient first (POST /api/demo/seed).
      </p>
    );
  }

  return (
    <div className="story-list">
      {events.map((event, i) => {
        const key = `${event.record_id}-${event.date}-${i}`;
        const open = openId === key;
        const isLatest = i === events.length - 1;
        return (
          <StaggerItem
            key={key}
            index={i}
            className={`story-item kind-${event.kind} ${isLatest ? "latest" : ""}`}
          >
            <button
              className="story-row"
              type="button"
              onClick={() => setOpenId(open ? null : key)}
              aria-expanded={open}
            >
              <span className="story-when">
                <span className="story-year">{event.date.slice(0, 4)}</span>
                <span className="story-date">{event.date}</span>
              </span>
              <span className="story-title">
                {event.title}
                {event.kind !== "visit" && (
                  <span className={`kind-chip kind-${event.kind}`}>
                    {KIND_LABEL[event.kind] ?? event.kind}
                  </span>
                )}
                {isLatest && <span className="kind-chip today">TODAY</span>}
              </span>
              <span className="story-rid" title="Source record">
                {event.record_id}
              </span>
            </button>

            {open && (
              <div className="story-detail">
                <p>{event.detail}</p>
                {event.record_id && (
                  <button
                    type="button"
                    className="linkish story-open-record"
                    onClick={() => onOpenRecord(event.record_id)}
                  >
                    Open source record {event.record_id} →
                  </button>
                )}
              </div>
            )}
          </StaggerItem>
        );
      })}
    </div>
  );
}
