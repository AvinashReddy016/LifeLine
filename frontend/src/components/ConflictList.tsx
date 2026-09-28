import type { Conflict } from "../services/api";

/**
 * Conflicts, in plain language. Never resolved automatically, never invented:
 * every item cites its two source records and stays UNRESOLVED.
 */
export function ConflictList({ conflicts, onOpenRecord }: { conflicts: Conflict[]; onOpenRecord: (id: string) => void }) {
  if (!conflicts.length) {
    return <p className="empty-note">No potential conflicts detected by the rule-based scan.</p>;
  }
  return (
    <div className="conflict-section">
      <p className="conflict-banner">
        {conflicts.length} potential conflict{conflicts.length === 1 ? "" : "s"} — never
        auto-resolved
      </p>
      {conflicts.map((conflict) => (
        <div key={conflict.conflict_id} className="conflict-item">
          <div className="conflict-item-type">{conflict.type.replace(/_/g, " ")}</div>
          <p className="conflict-item-desc">{conflict.description}</p>
          <div className="conflict-item-claims">
            <div className="conflict-claim">
              <button
                type="button"
                className="rid"
                onClick={() => onOpenRecord(conflict.record_a_id)}
              >
                {conflict.record_a_id} · {conflict.record_a_date}
              </button>
              <div>“{conflict.record_a_claim}”</div>
            </div>
            <div className="conflict-claim">
              <button
                type="button"
                className="rid"
                onClick={() => onOpenRecord(conflict.record_b_id)}
              >
                {conflict.record_b_id} · {conflict.record_b_date}
              </button>
              <div>“{conflict.record_b_claim}”</div>
            </div>
          </div>
          <div className="conflict-item-status">
            Status: UNRESOLVED — clinician verification required.
          </div>
        </div>
      ))}
    </div>
  );
}
