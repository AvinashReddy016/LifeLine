const API_BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

export interface Patient {
  patient_id: string;
  name: string;
  age: number;
  sex: string;
  blood_type: string;
  current_issue: string;
  current_medications: string[];
  is_synthetic: boolean;
}

export interface TimelineEvent {
  date: string;
  record_id: string;
  record_type: string;
  title: string;
  kind: string;
  detail: string;
  highlight: boolean;
}

export interface MemoryRef {
  id: string;
  text: string;
  score: number;
  memory_type: string;
  dimension: string;
  record_ids: string[];
  date: string;
}

export interface Conflict {
  conflict_id: string;
  patient_id: string;
  type: string;
  description: string;
  record_a_id: string;
  record_a_date: string;
  record_a_claim: string;
  record_b_id: string;
  record_b_date: string;
  record_b_claim: string;
  status: string;
  required_action: string;
}

export interface ChatResponse {
  answer: string;
  memories_used: MemoryRef[];
  source_records: { record_id: string; date: string; title: string; summary: string; body: string; facility: string; clinician: string }[];
  timeline_events: TimelineEvent[];
  conflicts: Conflict[];
  uncertainty: string[];
  safety_note: string;
}

export interface JourneyStage {
  stage: number;
  interactions: number;
  records_in_memory: number;
  memories_retained: number;
  memories_recalled: number;
  records_linked: string[];
  record_count: number;
  dates_covered: string[];
  recall_available: boolean;
  preview: string[];
  error?: string;
}

export interface JourneyStory {
  question: string;
  patient_id: string;
  stages: JourneyStage[];
  note: string;
  error?: string;
}

export interface Record_ {
  record_id: string;
  date: string;
  record_type: string;
  title: string;
  facility: string;
  clinician: string;
  summary: string;
  body: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  getPatients: () => request<{ patients: Patient[] }>(`/api/patients`),
  getPatient: (id: string) => request<{ patient: Patient }>(`/api/patients/${id}`),
  getRecords: (id: string) => request<{ records: Record_[]; count: number }>(`/api/patients/${id}/records`),
  getTimeline: (id: string) => request<{ events: TimelineEvent[] }>(`/api/patients/${id}/timeline`),
  getConflicts: (id: string) => request<{ conflicts: Conflict[] }>(`/api/patients/${id}/conflicts`),
  getMemoryStatus: (patientId?: string) =>
    request<{ available: boolean; memory_count?: number; bank_id?: string; reason?: string }>(
      `/api/memory/status${patientId ? `?patient_id=${encodeURIComponent(patientId)}` : ""}`),
  chat: (patientId: string, question: string) =>
    request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ patient_id: patientId, question }) }),
  handoff: (patientId: string) =>
    request<{ patient_id: string; generated_at: string; sections: Record<string, string>; records_reviewed: string[]; safety_note: string }>(
      "/api/handoff", { method: "POST", body: JSON.stringify({ patient_id: patientId }) }),
  demoMode: (question: string, patientId?: string) => {
    const params = new URLSearchParams({ question });
    if (patientId) params.set("patient_id", patientId);
    return request<any>(`/api/demo/mode?${params.toString()}`);
  },
  memoryJourney: (patientId?: string) => {
    const qs = patientId ? `?patient_id=${encodeURIComponent(patientId)}` : "";
    return request<JourneyStory>(`/api/demo/journey${qs}`);
  },
};
