import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type ApplicationDetail, type JobInput, type Status } from './api'
import { IconClose, IconDoc } from './icons'

export type FormState =
  | { mode: 'create'; status?: Status }
  | { mode: 'edit'; app: ApplicationDetail }

const CURRENCIES = ['', 'USD', 'EUR', 'RUB', 'GBP']

function initial(state: FormState): JobInput {
  if (state.mode === 'edit') {
    const a = state.app
    return {
      company: a.company,
      company_url: a.company_url ?? '',
      title: a.title,
      description: a.description ?? '',
      found_via: a.found_via ?? '',
      found_url: a.found_url ?? '',
      location: a.location ?? '',
      work_mode: a.work_mode ?? '',
      salary_min: a.salary_min ?? null,
      salary_max: a.salary_max ?? null,
      currency: a.currency ?? '',
      applied_via: a.applied_via,
      applied_ref: a.applied_ref ?? '',
      direction: a.direction ?? 'outbound',
      status: a.status,
      priority: a.priority ?? '',
      cover_letter: a.cover_letter ?? '',
      contact_name: a.contact_name ?? '',
      contact_email: a.contact_email ?? '',
      contact_url: a.contact_url ?? '',
      next_action: a.next_action ?? '',
      next_action_date: a.next_action_date ?? '',
      tags: a.tags ?? [],
    }
  }
  return {
    company: '',
    company_url: '',
    title: '',
    description: '',
    found_via: '',
    found_url: '',
    location: '',
    work_mode: '',
    salary_min: null,
    salary_max: null,
    currency: '',
    applied_via: 'other',
    applied_ref: '',
    direction: 'outbound',
    status: state.status ?? 'saved',
    priority: '',
    cover_letter: '',
    contact_name: '',
    contact_email: '',
    contact_url: '',
    next_action: '',
    next_action_date: '',
    tags: [],
  }
}

export function JobForm({ state, onClose }: { state: FormState; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: api.meta })
  const [init] = useState(() => initial(state))
  const [f, setF] = useState<JobInput>(init)
  const [tagsText, setTagsText] = useState((init.tags ?? []).join(', '))

  // Resume is a file, uploaded to its own endpoint after the job is saved.
  const fileRef = useRef<HTMLInputElement>(null)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [removeResume, setRemoveResume] = useState(false)
  const savedName = state.mode === 'edit' ? state.app.resume_filename ?? null : null

  function set<K extends keyof JobInput>(k: K, v: JobInput[K]) {
    setF((p) => ({ ...p, [k]: v }))
  }

  function clearPick() {
    setResumeFile(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const mutation = useMutation({
    mutationFn: async () => {
      // Empty optional strings → null so we don't store "".
      const payload: JobInput = {
        ...f,
        company: f.company.trim(),
        company_url: f.company_url || null,
        title: f.title.trim(),
        description: f.description?.trim() || '',
        tags: tagsText.split(',').map((t) => t.trim()).filter(Boolean),
        found_via: f.found_via || null,
        found_url: f.found_url || null,
        applied_ref: f.applied_ref || null,
        location: f.location || null,
        work_mode: f.work_mode || null,
        currency: f.currency || null,
        cover_letter: f.cover_letter || null,
        contact_name: f.contact_name || null,
        contact_email: f.contact_email || null,
        contact_url: f.contact_url || null,
        priority: f.priority || null,
        next_action: f.next_action || null,
        next_action_date: f.next_action_date || null,
      }
      if (state.mode === 'create') {
        const created = await api.create(payload)
        if (resumeFile) await api.uploadResume(created.id, resumeFile)
        return created
      }

      // Edit: a status change must go through the status endpoint so it logs a
      // timeline event and sets applied_at (a plain PATCH would do neither).
      const id = state.app.id
      if (payload.status && payload.status !== state.app.status) {
        await api.changeStatus(id, payload.status)
      }
      const patch: Partial<JobInput> = { ...payload }
      delete patch.status
      const updated = await api.update(id, patch)
      // A newly picked file replaces whatever was there; otherwise honour an
      // explicit removal. No file + no removal = leave the resume untouched.
      if (resumeFile) await api.uploadResume(id, resumeFile)
      else if (removeResume) await api.deleteResume(id)
      return updated
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['apps'] })
      qc.invalidateQueries({ queryKey: ['metrics'] })
      if (state.mode === 'edit') qc.invalidateQueries({ queryKey: ['app', state.app.id] })
      onClose()
    },
  })

  const canSave = Boolean(f.company.trim() && f.title.trim()) && !mutation.isPending

  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{state.mode === 'create' ? 'Add job' : 'Edit job'}</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>
            <IconClose />
          </button>
        </div>

        <form
          className="modal-body"
          onSubmit={(e) => {
            e.preventDefault()
            if (canSave) mutation.mutate()
          }}
        >
          <div className="form-grid">
            <label className="field span2">
              <span>Company *</span>
              <input value={f.company} onChange={(e) => set('company', e.target.value)} required autoFocus />
            </label>
            <label className="field span2">
              <span>Role / title *</span>
              <input value={f.title} onChange={(e) => set('title', e.target.value)} required />
            </label>

            <label className="field">
              <span>Status</span>
              <select value={f.status} onChange={(e) => set('status', e.target.value as Status)}>
                {meta?.statuses.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Applied via</span>
              <select value={f.applied_via} onChange={(e) => set('applied_via', e.target.value)}>
                {(meta?.applied_via ?? []).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Direction</span>
              <select
                value={f.direction ?? 'outbound'}
                onChange={(e) => set('direction', e.target.value as 'inbound' | 'outbound')}
              >
                {(meta?.directions ?? ['outbound', 'inbound']).map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Priority</span>
              <select value={f.priority ?? ''} onChange={(e) => set('priority', e.target.value)}>
                <option value="">—</option>
                {(meta?.priorities ?? ['high', 'medium', 'low']).map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>Work mode</span>
              <select value={f.work_mode ?? ''} onChange={(e) => set('work_mode', e.target.value)}>
                <option value="">—</option>
                {(meta?.work_modes ?? []).map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Location</span>
              <input value={f.location ?? ''} onChange={(e) => set('location', e.target.value)} />
            </label>

            <label className="field">
              <span>Salary min</span>
              <input
                type="number"
                value={f.salary_min ?? ''}
                onChange={(e) => set('salary_min', e.target.value ? Number(e.target.value) : null)}
              />
            </label>
            <label className="field">
              <span>Salary max</span>
              <input
                type="number"
                value={f.salary_max ?? ''}
                onChange={(e) => set('salary_max', e.target.value ? Number(e.target.value) : null)}
              />
            </label>

            <label className="field">
              <span>Currency</span>
              <select value={f.currency ?? ''} onChange={(e) => set('currency', e.target.value)}>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{c || '—'}</option>
                ))}
              </select>
            </label>
            <div className="field span2">
              <span>Resume (PDF / DOC — the file you sent)</span>
              {resumeFile ? (
                <div className="doc-line">
                  <IconDoc />
                  <span className="fname">{resumeFile.name}</span>
                  <span className="tag">new</span>
                  <button type="button" className="file-x" onClick={clearPick}>Clear</button>
                </div>
              ) : savedName && !removeResume ? (
                <div className="doc-line">
                  <IconDoc />
                  <span className="fname">{savedName}</span>
                  <button type="button" className="file-x" onClick={() => setRemoveResume(true)}>Remove</button>
                </div>
              ) : removeResume ? (
                <div className="doc-line muted">
                  <span className="fname">Will be removed on save</span>
                  <button type="button" className="file-x" onClick={() => setRemoveResume(false)}>Undo</button>
                </div>
              ) : null}
              <label className="file-btn">
                <IconDoc />
                {resumeFile || (savedName && !removeResume) ? 'Replace file…' : 'Choose file…'}
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf"
                  onChange={(e) => { setResumeFile(e.target.files?.[0] ?? null); setRemoveResume(false) }}
                />
              </label>
            </div>

            <label className="field span2">
              <span>Company site (URL)</span>
              <input value={f.company_url ?? ''} onChange={(e) => set('company_url', e.target.value)} placeholder="https://…" />
            </label>
            <label className="field">
              <span>Found via</span>
              <select value={f.found_via ?? ''} onChange={(e) => set('found_via', e.target.value)}>
                <option value="">—</option>
                {(meta?.found_via ?? []).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Found at (URL)</span>
              <input value={f.found_url ?? ''} onChange={(e) => set('found_url', e.target.value)} placeholder="https://…" />
            </label>
            <label className="field span2">
              <span>Applied to (URL or email)</span>
              <input value={f.applied_ref ?? ''} onChange={(e) => set('applied_ref', e.target.value)}
                     placeholder="https://careers…/apply  ·  jobs@company.com" />
            </label>

            <label className="field span2">
              <span>Description (JD)</span>
              <textarea rows={4} value={f.description ?? ''} onChange={(e) => set('description', e.target.value)} />
            </label>
            <label className="field span2">
              <span>Cover letter / message</span>
              <textarea rows={3} value={f.cover_letter ?? ''} onChange={(e) => set('cover_letter', e.target.value)} />
            </label>

            <label className="field">
              <span>Contact name</span>
              <input value={f.contact_name ?? ''} onChange={(e) => set('contact_name', e.target.value)} />
            </label>
            <label className="field">
              <span>Contact email</span>
              <input type="email" value={f.contact_email ?? ''} onChange={(e) => set('contact_email', e.target.value)} />
            </label>
            <label className="field span2">
              <span>Contact URL (LinkedIn)</span>
              <input value={f.contact_url ?? ''} onChange={(e) => set('contact_url', e.target.value)} />
            </label>

            <label className="field">
              <span>Next action</span>
              <input value={f.next_action ?? ''} onChange={(e) => set('next_action', e.target.value)} />
            </label>
            <label className="field">
              <span>Next action date</span>
              <input type="date" value={f.next_action_date ?? ''} onChange={(e) => set('next_action_date', e.target.value)} />
            </label>

            <label className="field span2">
              <span>Tags (comma-separated)</span>
              <input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="python, postgres" />
            </label>
          </div>

          {mutation.isError && <p className="form-error">Could not save. Check the fields and try again.</p>}

          <div className="modal-foot">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={!canSave}>
              {mutation.isPending ? 'Saving…' : state.mode === 'create' ? 'Add job' : 'Save changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
