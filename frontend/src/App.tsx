import { useEffect, useState } from "react";
import { HomePage } from "./pages/HomePage";
import { PatientPage } from "./pages/PatientPage";

type View = "home" | "patient";

export default function App() {
  const [view, setView] = useState<View>(() =>
    new URLSearchParams(window.location.search).get("view") === "patient" ? "patient" : "home"
  );

  // Which workspace tab to land on when the workspace is opened from the
  // homepage ("Explore Memory" jumps straight to the Memory view).
  const [tab, setTab] = useState<string | null>(null);

  // Keep the URL shareable (e.g. http://localhost:5173/?view=patient opens the
  // workspace directly — handy for demos and for automated verification).
  useEffect(() => {
    const url = new URL(window.location.href);
    if (view === "patient") {
      url.searchParams.set("view", "patient");
    } else {
      url.searchParams.delete("view");
      url.searchParams.delete("tab");
    }
    window.history.replaceState(null, "", url);
  }, [view]);

  function openPatient(nextTab: string | null = null) {
    setTab(nextTab);
    setView("patient");
  }

  return view === "home" ? (
    <HomePage onOpenPatient={() => openPatient()} onExploreMemory={() => openPatient("memory")} />
  ) : (
    <PatientPage onHome={() => setView("home")} initialTab={tab} />
  );
}
