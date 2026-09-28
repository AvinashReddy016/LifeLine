"""Temporary visual-verification mock backend.

Serves the LifeLine API contract with canned responses for each answer case
(table findings, conflicts, and the no-records case) so the real frontend UI
can be driven and asserted in headless Chrome.

Usage: python visual_test/mock_backend.py   (port 8001, Ctrl+C to stop)

NOTE: This file is for VISUAL TESTING ONLY. The real application backend is
backend/app — nothing in the product imports from here.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

PATIENT = {
    "patient_id": "P-001",
    "name": "Arjun Mehra",
    "age": 34,
    "sex": "Male",
    "blood_type": "O+",
    "photo_color": "#0f766e",
    "is_synthetic": True,
    "baseline_allergies": [],
    "baseline_conditions": [],
    "current_medications": ["Amlodipine 2.5 mg daily", "Pantoprazole 20 mg daily"],
    "current_issue": "Recurrent dizziness with one near-syncopal episode",
    "current_context_note": "",
}

RECORDS = {
    "REC-1006": {
        "record_id": "REC-1006",
        "date": "2024-02-14",
        "record_type": "visit",
        "title": "Initial cardiology consultation",
        "facility": "City General Hospital",
        "clinician": "Dr. S. Rao",
        "summary": "Hypertension evaluation; penicillin allergy documented; started on metoprolol.",
        "body": "Blood pressure 148/92 mmHg. Penicillin allergy noted per patient report. Metoprolol 25 mg daily started.",
    },
    "REC-1011": {
        "record_id": "REC-1011",
        "date": "2024-11-03",
        "record_type": "discharge",
        "title": "Hospital discharge summary",
        "facility": "City General Hospital",
        "clinician": "Dr. M. Iyer",
        "summary": "Discharged after chest-pain observation; medication switched to amlodipine.",
        "body": "Observation stay 48h, troponins negative. Metoprolol switched to Amlodipine 2.5 mg daily at discharge.",
    },
    "REC-1014": {
        "record_id": "REC-1014",
        "date": "2025-01-20",
        "record_type": "followup",
        "title": "Cardiology follow-up",
        "facility": "Sunrise Clinic",
        "clinician": "Dr. S. Rao",
        "summary": "BP improved on amlodipine; dizziness reported as occasional.",
        "body": "BP 138/86 mmHg. Patient reports occasional dizziness in the mornings. Continue current dose.",
    },
    "REC-1018": {
        "record_id": "REC-1018",
        "date": "2025-06-02",
        "record_type": "prescription",
        "title": "Prescription renewal",
        "facility": "Sunrise Clinic",
        "clinician": "Dr. P. Nair",
        "summary": "Amoxicillin prescribed for dental infection despite documented penicillin allergy.",
        "body": "Amoxicillin 500 mg TID for 7 days issued for dental infection. Allergy field lists penicillin.",
    },
}

CONFLICTS = [
    {
        "conflict_id": "CF-REC-1006-REC-1018-penicillin",
        "patient_id": "P-001",
        "type": "allergy_vs_medication",
        "description": "Penicillin is listed as an allergy, but amoxicillin (a penicillin-class antibiotic) was prescribed later.",
        "record_a_id": "REC-1006",
        "record_a_date": "2024-02-14",
        "record_a_claim": "Patient reports penicillin allergy; documented in allergy field.",
        "record_b_id": "REC-1018",
        "record_b_date": "2025-06-02",
        "record_b_claim": "Amoxicillin 500 mg prescribed for dental infection.",
        "status": "UNRESOLVED",
        "required_action": "Verify against the current clinical record.",
    },
    {
        "conflict_id": "CF-REC-1006-REC-1011-metoprolol",
        "patient_id": "P-001",
        "type": "value_discrepancy",
        "description": "Metoprolol documented as started in 2024 but recorded as discontinued at discharge.",
        "record_a_id": "REC-1006",
        "record_a_date": "2024-02-14",
        "record_a_claim": "Metoprolol 25 mg daily started for hypertension.",
        "record_b_id": "REC-1011",
        "record_b_date": "2024-11-03",
        "record_b_claim": "Metoprolol switched to amlodipine at discharge.",
        "status": "UNRESOLVED",
        "required_action": "Verify against the current clinical record.",
    },
]

MEMORIES_EVIDENCE = [
    {
        "id": "mem-evidence-1",
        "text": "Discharged after chest-pain observation; metoprolol switched to amlodipine 2.5 mg daily (REC-1011).",
        "score": 0.91,
        "memory_type": "experience",
        "dimension": "medication_history",
        "record_ids": ["REC-1011"],
        "date": "2024-11-03",
    },
    {
        "id": "mem-evidence-2",
        "text": "Cardiology follow-up: BP 138/86 mmHg on amlodipine, occasional morning dizziness reported (REC-1014).",
        "score": 0.84,
        "memory_type": "experience",
        "dimension": "recent_changes",
        "record_ids": ["REC-1014"],
        "date": "2025-01-20",
    },
    {
        "id": "mem-evidence-3",
        "text": "Initial cardiology consultation: BP 148/92 mmHg, penicillin allergy documented, metoprolol started (REC-1006).",
        "score": 0.77,
        "memory_type": "fact",
        "dimension": "direct",
        "record_ids": ["REC-1006"],
        "date": "2024-02-14",
    },
]

MEMORIES_CONFLICT = [
    {
        "id": "mem-conflict-1",
        "text": "Penicillin allergy documented at initial consultation (REC-1006).",
        "score": 0.88,
        "memory_type": "fact",
        "dimension": "conflicts",
        "record_ids": ["REC-1006"],
        "date": "2024-02-14",
    },
    {
        "id": "mem-conflict-2",
        "text": "Amoxicillin prescribed for dental infection despite allergy field (REC-1018).",
        "score": 0.86,
        "memory_type": "experience",
        "dimension": "conflicts",
        "record_ids": ["REC-1018"],
        "date": "2025-06-02",
    },
]

ANSWER_CHANGES = """The patient's antihypertensive was switched after the last hospital stay, and blood pressure control improved on the current regimen.

**Key changes since the last hospital visit:**

| What changed | Previous | Current | Source |
|---|---|---|---|
| Medication | Metoprolol 25 mg daily | Amlodipine 2.5 mg daily | `REC-1011` |
| Blood pressure | 148/92 mmHg | 138/86 mmHg | `REC-1014` |
| Dizziness | Not documented | Occasional morning episodes | `REC-1014` |

- Discharge was after a 48-hour chest-pain observation with negative troponins
- The current chart also lists pantoprazole 20 mg daily, not present in earlier notes

**Clinician verification needed:** confirm the reason for the metoprolol-to-amlodipine switch documented in `REC-1011`."""

ANSWER_CONFLICTS = """Potential conflicts were detected between the documented allergy entry and later prescriptions.

| Information | Record | Status |
|---|---|---|
| Penicillin listed as allergy | `REC-1006` | Verify |
| Amoxicillin (penicillin-class) prescribed | `REC-1018` | Verify |
| Metoprolol started vs. switched | `REC-1006` / `REC-1011` | Verify |

These conflicts are **unresolved** and require clinician verification."""

ANSWER_NO_RECORDS = """No historical records were found for this question.

**Key points a clinician should verify:**

| Domain | Specific items to confirm |
|---|---|
| **Symptom characterization** | Frequency, duration, triggers, and associated features |
| **Cardiovascular history** | Prior hypertension control, arrhythmias, structural heart disease |
| **Medication review** | Current medications, recent dose changes, possible side effects |
| **Recent investigations** | Blood pressure, ECG, labs, imaging |
| **Lifestyle & risk factors** | Caffeine, sleep, hydration, alcohol intake |"""


def chat_payload(question: str) -> dict:
    safety = (
        "LifeLine organizes documented history only. It does not diagnose or treat. "
        "All items must be verified by a clinician."
    )
    q = question.lower()
    if "conflict" in q:
        return {
            "answer": ANSWER_CONFLICTS,
            "memories_used": MEMORIES_CONFLICT,
            "source_records": [RECORDS["REC-1006"], RECORDS["REC-1011"]],
            "timeline_events": [],
            "conflicts": CONFLICTS,
            "uncertainty": ["Allergy status could not be verified against primary documents."],
            "safety_note": safety,
        }
    if "changed" in q or "similar symptoms" in q:
        return {
            "answer": ANSWER_CHANGES,
            "memories_used": MEMORIES_EVIDENCE,
            "source_records": [RECORDS["REC-1006"], RECORDS["REC-1011"], RECORDS["REC-1014"]],
            "timeline_events": [],
            "conflicts": [],
            "uncertainty": [],
            "safety_note": safety,
        }
    # Case 4: genuinely no historical records recalled.
    return {
        "answer": ANSWER_NO_RECORDS,
        "memories_used": [],
        "source_records": [],
        "timeline_events": [],
        "conflicts": [],
        "uncertainty": [],
        "safety_note": safety,
    }


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/patients":
            self._json({"patients": [PATIENT], "synthetic": True})
        elif re.fullmatch(r"/api/patients/[^/]+", path):
            self._json({"patient": PATIENT, "synthetic": True})
        elif re.fullmatch(r"/api/patients/[^/]+/timeline", path):
            self._json({"events": [], "synthetic": True})
        elif re.fullmatch(r"/api/patients/[^/]+/conflicts", path):
            self._json({"conflicts": CONFLICTS, "status": "UNRESOLVED — clinician verification required", "synthetic": True})
        elif re.fullmatch(r"/api/patients/[^/]+/records", path):
            self._json({"records": list(RECORDS.values()), "count": len(RECORDS), "synthetic": True})
        elif m := re.fullmatch(r"/api/records/(REC-\d+)", path):
            rec = RECORDS.get(m.group(1))
            self._json({"record": rec, "synthetic": True}, 200 if rec else 404)
        elif path == "/api/memory/status":
            self._json({"available": True, "memory_count": 128, "bank_id": "mock-bank"})
        else:
            self._json({"detail": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else "{}"
        if path == "/api/chat":
            req = json.loads(body or "{}")
            self._json(chat_payload(req.get("question", "")))
        elif path == "/api/handoff":
            self._json({
                "patient_id": PATIENT["patient_id"],
                "generated_at": "2026-09-28T00:00:00",
                "sections": {},
                "records_reviewed": [],
                "safety_note": "Mock safety note.",
            })
        else:
            self._json({"detail": "not found"}, 404)

    def log_message(self, fmt: str, *args) -> None:  # keep the console quiet
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8001), Handler)
    print("Mock LifeLine backend on http://127.0.0.1:8001 (visual test only)")
    server.serve_forever()
