import { SyntheticBanner } from "./Chrome";
import { PatientBanner } from "./PatientBanner";
import { MainNav } from "./MainNav";

export function WorkspaceLayout({
  patient,
  activeView,
  onNavigate,
  recordCount,
  conflictCount,
  memoryCount,
  memoryAvailable,
}: {
  patient: any;
  activeView: string;
  onNavigate: (v: string) => void;
  recordCount: number;
  conflictCount: number;
  memoryCount: number | null;
  memoryAvailable: boolean;
}) {
  return (
    <>
      <SyntheticBanner />
      <main className="workspace-new">
        {patient && (
          <PatientBanner
            patient={patient}
            recordCount={recordCount}
            conflictCount={conflictCount}
            memoryCount={memoryCount}
            memoryAvailable={memoryAvailable}
          />
        )}
        <MainNav view={activeView} onChange={onNavigate} />
      </main>
    </>
  );
}
