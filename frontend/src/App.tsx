import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type ApplicationDetail, type Status } from './api'
import { BoardView } from './Board'
import { TableView, MetricsView } from './Views'
import { JobForm, type FormState } from './JobForm'
import { IconClock, IconCode, IconPlus, IconSearch, IconSun } from './icons'

type View = 'board' | 'table' | 'metrics'

const TABS: { key: View; label: string }[] = [
  { key: 'board', label: 'Board' },
  { key: 'table', label: 'Table' },
  { key: 'metrics', label: 'Metrics' },
]

// Topbar "needs action" chip: jobs with a due or overdue next action.
function NeedsAction({ onOpen }: { onOpen: (id: number) => void }) {
  const { data: m } = useQuery({ queryKey: ['metrics'], queryFn: api.metrics })
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const items = m?.follow_ups ?? []
  const overdue = items.filter((f) => f.overdue_days > 0).length

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [open])

  return (
    <div className="today-wrap" ref={ref}>
      <button
        className="today-chip"
        title="Show what needs action"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
      >
        <IconClock size={14} />
        <span>
          <b>{items.length}</b> to do
          {overdue ? (
            <>
              {' · '}
              <span className="od">{overdue} overdue</span>
            </>
          ) : null}
        </span>
      </button>
      {open && (
        <div className="today-pop">
          <div className="tp-head">Needs action</div>
          <div className="tp-list">
            {items.map((f) => (
              <button className="tp-item" key={f.id} onClick={() => { setOpen(false); onOpen(f.id) }}>
                <div className="tp-main">
                  <div className="tp-role">{f.title}</div>
                  <div className="tp-co">{f.company}</div>
                </div>
                <span className={`next ${f.overdue_days > 0 ? 'overdue' : 'soon'}`}>
                  {f.overdue_days > 0 ? `overdue ${f.overdue_days}d` : 'today'}
                </span>
              </button>
            ))}
            {!items.length && <div className="tp-head" style={{ opacity: 0.7 }}>Nothing due 👌</div>}
          </div>
        </div>
      )}
    </div>
  )
}

function TopBar({
  view,
  onView,
  onToggleTheme,
  onOpen,
  onAdd,
}: {
  view: View
  onView: (v: View) => void
  onToggleTheme: () => void
  onOpen: (id: number) => void
  onAdd: () => void
}) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="mark" aria-hidden>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.4">
            <circle cx="12" cy="12" r="8" />
            <circle cx="12" cy="12" r="2.6" fill="#fff" stroke="none" />
          </svg>
        </span>
        Application Tracker
      </div>

      <div className="seg" role="tablist" aria-label="Views">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={view === t.key} onClick={() => onView(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      <NeedsAction onOpen={onOpen} />

      <div className="search" aria-hidden>
        <IconSearch />
        <span>Search by company, role…</span>
        <kbd>⌘K</kbd>
      </div>
      <button className="icon-btn" title="Toggle theme" aria-label="Toggle theme" onClick={onToggleTheme}>
        <IconSun />
      </button>
      <button className="btn-primary" onClick={onAdd}>
        <IconPlus /> Add
      </button>
    </header>
  )
}

function Footer() {
  return (
    <div className="footer-note">
      <IconCode />
      Updated from the web and via the <code>tracker</code> CLI — Claude moves statuses and writes notes itself
      <span className="spacer" />
      <span className="mono" style={{ fontSize: 11 }}>SQLite · FastAPI · React + TS</span>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>('board')
  const [selected, setSelected] = useState<number | null>(null)
  const [form, setForm] = useState<FormState | null>(null)

  const toggleTheme = () => {
    const root = document.documentElement
    const cur = root.getAttribute('data-theme')
    const isDark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
    root.setAttribute('data-theme', isDark ? 'light' : 'dark')
  }

  const openJob = (id: number) => {
    setSelected(id)
    setView('board')
  }

  return (
    <div className="app">
      <TopBar
        view={view}
        onView={setView}
        onToggleTheme={toggleTheme}
        onOpen={openJob}
        onAdd={() => setForm({ mode: 'create' })}
      />
      <div className="main">
        {view === 'board' && (
          <BoardView
            selected={selected}
            onSelect={setSelected}
            onEdit={(app: ApplicationDetail) => setForm({ mode: 'edit', app })}
            onCreate={(status?: Status) => setForm({ mode: 'create', status })}
          />
        )}
        {view === 'table' && <TableView onOpen={openJob} />}
        {view === 'metrics' && <MetricsView />}
      </div>
      <Footer />
      {form && <JobForm state={form} onClose={() => setForm(null)} />}
    </div>
  )
}
