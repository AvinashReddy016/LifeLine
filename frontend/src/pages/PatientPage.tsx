import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { SyntheticBanner } from "../components/Chrome";
import { TopBar } from "../components/TopBar";
import { PatientBanner } from "../components/PatientBanner";
import { MainNav } from "../components/MainNav";
import { AskLifeLine } from "../components/AskLifeLine";
import { PatientStory } from "../components/PatientStory";
import { HandoffDoc } from "../components/HandoffDoc";
import { MemoryFlow } from "../components/MemoryFlow";
import { WhyMemoryMatters } from "../components/WhyMemoryMatters";
import { MemoryJourney } from "../components/MemoryJourney";
import { RecordModal } from "../components/RecordModal";
import { ConflictList } from "../components/ConflictList";
import {
  api,
  type Conflict as ConflictType,
  type Patient,
  type TimelineEvent,
} from "../services/api";

type View = "ask" | "story" | "handoff" | "memory";

const VIEWS: View[] = ["ask", "story", "handoff", "memory"];

function coerceView(value: string | null | undefined): View | null {
  return value && (VIEWS as string[]).includes(value) ? (value as View) : null;
}

function initialView(): View {
  return coerceView(new URLSearchParams(window.location.search).get("tab")) ?? "ask";
}

export function PatientPage({
  onHome,
  initialTab,
}: {
  onHome: () => void;
  initialTab?: string | null;
}) {
  const [patientId, setPatientId] = useState("");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [conflicts, setConflicts] = useState<ConflictType[]>([]);
  const [memoryCount, setMemoryCount] = useState<number | null>(null);
  // `null` = still loading, so the header pill can say "checking…" instead of
  // briefly claiming "offline".
  const [memoryAvailable, setMemoryAvailable] = useState<boolean | null>(null);
  const [view, setView] = useState<View>(() => coerceView(initialTab) ?? initialView());
  const [openRecordId, setOpenRecordId] = useState<string | null>(null);

  const reduce = useReducedMotion();

  // Keep the active view in the URL (e.g. /?view=patient&tab=handoff) so demo
  // states are shareable/bookmarkable.
  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", view);
    window.history.replaceState(null, "", url);
  }, [view]);

  useEffect(() => {
    api
      .getPatients()
      .then((res) => {
        if (!res.patients.length) throw new Error("No patients found. Seed first.");
        const first = [...res.patients].sort((a, b) => a.patient_id.localeCompare(b.patient_id))[0];
        setPatientId(first.patient_id);
      })
      .catch(() => setPatientId(""));
  }, []);

  useEffect(() => {
    if (!patientId) return;
    api
      .getPatient(patientId)
      .then((res) => setPatient(res.patient))
      .catch(() => setPatient(null));
    api
      .getTimeline(patientId)
      .then((res) => setEvents(res.events))
      .catch(() => setEvents([]));
    api
      .getConflicts(patientId)
      .then((res) => setConflicts(res.conflicts))
      .catch(() => setConflicts([]));
    api
      .getMemoryStatus(patientId)
      .then((s) => {
        setMemoryAvailable(!!s.available);
        setMemoryCount(s.memory_count ?? null);
      })
      .catch(() => {
        setMemoryAvailable(false);
        setMemoryCount(null);
      });
  }, [patientId]);

  const openRecord = (id: string) => setOpenRecordId(id);

  return (
    <>
      <SyntheticBanner />
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <TopBar onHome={onHome} memoryCount={memoryCount} memoryAvailable={memoryAvailable} />

      <main className="workspace-new" id="main">
        <PatientBanner
          patient={patient}
          recordCount={events.length}
          conflictCount={conflicts.length}
          memoryCount={memoryCount}
          memoryAvailable={memoryAvailable === true}
        />

        <MainNav view={view} onChange={(v) => setView(coerceView(v) ?? "ask")} />

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            className="view-area"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 1 } : { opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            {view === "ask" && (
              <>
                <AskLifeLine patientId={patientId} onOpenRecord={openRecord} />
                {conflicts.length > 0 && (
                  <section className="view-conflicts">
                    <h2 className="memory-flow-title">Potential conflicts</h2>
                    <ConflictList conflicts={conflicts} onOpenRecord={openRecord} />
                  </section>
                )}
              </>
            )}

            {view === "story" && (
              <>
                <section className="story-view">
                  <h2 className="memory-flow-title">Patient story</h2>
                  <p className="story-sub">
                    Chronological history reconstructed from {events.length} records. Select an
                    event to expand it.
                  </p>
                  <PatientStory events={events} onOpenRecord={openRecord} />
                </section>
                {conflicts.length > 0 && (
                  <section className="view-conflicts">
                    <h2 className="memory-flow-title">Potential conflicts</h2>
                    <ConflictList conflicts={conflicts} onOpenRecord={openRecord} />
                  </section>
                )}
                <section className="story-why">
                  <WhyMemoryMatters patientId={patientId} />
                </section>
              </>
            )}

            {view === "handoff" && (
              <HandoffDoc patientId={patientId} onBack={() => setView("story")} />
            )}

            {view === "memory" && (
              <>
                <MemoryFlow patientId={patientId} />
                <section className="story-why">
                  <WhyMemoryMatters patientId={patientId} />
                </section>
                <section className="story-why">
                  <MemoryJourney patientId={patientId} />
                </section>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      {openRecordId && (
        <RecordModal
          recordId={openRecordId}
          patientId={patientId}
          onClose={() => setOpenRecordId(null)}
        />
      )}
    </>
  );
}
