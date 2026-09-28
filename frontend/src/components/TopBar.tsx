import { useEffect, useState } from "react";
import { api } from "../services/api";

interface TopBarProps {
  /** When provided, the LifeLine wordmark becomes a button that returns home. */
  onHome?: () => void;
  /** Patient-scoped memory count. When omitted, the global count is fetched. */
  memoryCount?: number | null;
  /** Patient-scoped availability. `null` means "still loading". */
  memoryAvailable?: boolean | null;
}

/**
 * Minimal product header: LifeLine on the left, a single Hindsight status pill
 * on the right. The memory count is always live — never hardcoded. Until the
 * status resolves the pill reads "checking…" rather than claiming "offline".
 */
export function TopBar({ onHome, memoryCount, memoryAvailable }: TopBarProps) {
  const [status, setStatus] = useState<{
    available: boolean;
    memory_count?: number;
    bank_id?: string;
  } | null>(null);

  const controlled = memoryAvailable !== undefined;
  const pending = controlled ? memoryAvailable === null : status === null;
  const available = controlled ? memoryAvailable === true : Boolean(status?.available);
  const count = controlled ? memoryCount ?? 0 : status?.memory_count ?? 0;

  useEffect(() => {
    if (controlled) return;
    api.getMemoryStatus().then(setStatus).catch(() => setStatus({ available: false }));
  }, [controlled]);

  const label = available
    ? `Hindsight · ${count} memories`
    : pending
      ? "Hindsight · checking…"
      : "Hindsight · offline";

  return (
    <header className="topbar">
      <div className="topbar-inner">
        {onHome ? (
          <button
            type="button"
            className="logo logo-btn"
            onClick={onHome}
            aria-label="Back to the LifeLine homepage"
          >
            Life<span>Line</span>
          </button>
        ) : (
          <span className="logo">
            Life<span>Line</span>
          </span>
        )}

        <div className="topbar-right">
          <span
            className={`memory-chip ${available ? "live" : ""}`}
            title={
              status?.bank_id
                ? `Hindsight memory bank: ${status.bank_id}`
                : "Hindsight long-term memory status"
            }
          >
            <span className={`memory-dot ${available ? "live" : ""}`} aria-hidden="true" />
            {label}
          </span>
        </div>
      </div>
    </header>
  );
}
