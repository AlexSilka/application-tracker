// Typed client for the tracker REST API. Mirrors the backend schemas in
// tracker/models.py. (v2: generate these types from the OpenAPI schema.)

export type Status =
  | 'saved' | 'applied' | 'in_contact' | 'screening' | 'interview' | 'offer'
  | 'accepted' | 'rejected' | 'withdrawn' | 'ghosted'

export interface AppEvent {
  id: number
  application_id: number
  kind: string
  body: string
  meta?: Record<string, unknown> | null
  occurred_at: string
}

export interface Application {
  id: number
  company: string
  company_url?: string | null
  title: string
  description: string
  found_via?: string | null
  found_url?: string | null
  job_url?: string | null
  location?: string | null
  work_mode?: string | null
  salary_min?: number | null
  salary_max?: number | null
  currency?: string | null
  applied_via: string
  applied_ref?: string | null
  direction: 'inbound' | 'outbound'
  status: Status
  priority?: 'high' | 'medium' | 'low' | null
  cover_letter?: string | null
  contact_name?: string | null
  contact_email?: string | null
  contact_url?: string | null
  next_action?: string | null
  next_action_date?: string | null
  tags: string[]
  applied_at?: string | null
  created_at: string
  updated_at: string
  status_changed_at: string
}

export interface ApplicationDetail extends Application {
  resume_filename?: string | null
  events: AppEvent[]
}

// Shape accepted by create (POST) and update (PATCH). Mirrors ApplicationCreate /
// ApplicationUpdate in tracker/models.py. `company` and `title` are required on create.
export interface JobInput {
  company: string
  company_url?: string | null
  title: string
  description?: string
  found_via?: string | null
  found_url?: string | null
  job_url?: string | null
  location?: string | null
  work_mode?: string | null
  salary_min?: number | null
  salary_max?: number | null
  currency?: string | null
  applied_via?: string
  applied_ref?: string | null
  direction?: 'inbound' | 'outbound'
  status?: Status
  priority?: string | null
  cover_letter?: string | null
  contact_name?: string | null
  contact_email?: string | null
  contact_url?: string | null
  next_action?: string | null
  next_action_date?: string | null
  tags?: string[]
}

export interface StatusMeta {
  value: Status
  label: string
  active: boolean
  terminal: boolean
}

export interface Meta {
  statuses: StatusMeta[]
  active_statuses: Status[]
  terminal_statuses: Status[]
  found_via: string[]
  applied_via: string[]
  work_modes: string[]
  directions: string[]
  priorities: string[]
}

export interface Metrics {
  total: number
  active: number
  offers: number
  funnel: { applied: number; in_contact: number; screening: number; interview: number; offer: number; accepted: number }
  conversions: { applied_to_interview: number; interview_to_offer: number; response_rate: number }
  by_channel: { applied_via: string; applied: number; interview: number; rate: number }[]
  follow_ups: {
    id: number
    company: string
    title: string
    next_action?: string | null
    next_action_date?: string | null
    overdue_days: number
  }[]
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  meta: () => request<Meta>('/api/meta'),
  list: () => request<Application[]>('/api/applications'),
  get: (id: number) => request<ApplicationDetail>(`/api/applications/${id}`),
  metrics: () => request<Metrics>('/api/metrics'),
  changeStatus: (id: number, status: Status, note?: string) =>
    request<ApplicationDetail>(`/api/applications/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status, note }),
    }),
  addEvent: (id: number, kind: string, body: string) =>
    request<AppEvent>(`/api/applications/${id}/events`, {
      method: 'POST',
      body: JSON.stringify({ kind, body }),
    }),
  create: (body: JobInput) =>
    request<ApplicationDetail>('/api/applications', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  update: (id: number, patch: Partial<JobInput>) =>
    request<ApplicationDetail>(`/api/applications/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  remove: (id: number) =>
    request<void>(`/api/applications/${id}`, { method: 'DELETE' }),
  // Multipart upload: let the browser set the Content-Type boundary itself, so
  // this bypasses the JSON `request` helper.
  uploadResume: async (id: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`/api/applications/${id}/resume`, { method: 'POST', body: fd })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return (await res.json()) as ApplicationDetail
  },
  deleteResume: (id: number) =>
    request<void>(`/api/applications/${id}/resume`, { method: 'DELETE' }),
  resumeUrl: (id: number) => `/api/applications/${id}/resume`,
}
