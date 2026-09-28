const NAV: { key: string; label: string; hint: string }[] = [
  { key: "story", label: "Patient Story", hint: "Chronological longitudinal story" },
  { key: "ask", label: "Ask LifeLine", hint: "Question the patient's history" },
  { key: "handoff", label: "Handoff", hint: "Clinician handoff document" },
  { key: "memory", label: "Memory", hint: "How LifeLine remembers" },
];

export function MainNav({ view, onChange }: { view: string; onChange: (v: string) => void }) {
  return (
    <nav className="mainnav" aria-label="Patient views">
      {NAV.map((item) => {
        const active = view === item.key;
        return (
          <button
            key={item.key}
            type="button"
            className={`mainnav-tab ${active ? "active" : ""}`}
            onClick={() => onChange(item.key)}
            title={item.hint}
            aria-current={active ? "page" : undefined}
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
