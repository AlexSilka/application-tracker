import { useState } from 'react'
import { Kpis } from './Kpis'
import { BoardView } from './Board'
import { TableView, MetricsView } from './Views'
import { IconCode, IconPlus, IconSearch, IconSun } from './icons'

type View = 'board' | 'table' | 'metrics'

const TABS: { key: View; label: string }[] = [
  { key: 'board', label: 'Доска' },
  { key: 'table', label: 'Таблица' },
  { key: 'metrics', label: 'Метрики' },
]

function TopBar({
  view,
  onView,
  onToggleTheme,
}: {
  view: View
  onView: (v: View) => void
  onToggleTheme: () => void
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
        Отклики <span className="sub">поиск работы · 2026</span>
      </div>

      <div className="seg" role="tablist" aria-label="Виды">
        {TABS.map((t) => (
          <button key={t.key} role="tab" aria-selected={view === t.key} onClick={() => onView(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="search" aria-hidden>
        <IconSearch />
        <span>Поиск по компании, роли…</span>
        <kbd>⌘K</kbd>
      </div>
      <button className="icon-btn" title="Сменить тему" aria-label="Сменить тему" onClick={onToggleTheme}>
        <IconSun />
      </button>
      <button className="btn-primary">
        <IconPlus /> Добавить
      </button>
    </header>
  )
}

function Footer() {
  return (
    <div className="footer-note">
      <IconCode />
      Обновляется из веба и через <code>tracker</code> CLI — Claude сам двигает статусы и пишет заметки
      <span className="spacer" />
      <span className="mono" style={{ fontSize: 11 }}>SQLite · FastAPI · React + TS</span>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>('board')
  const [selected, setSelected] = useState<number | null>(null)

  const toggleTheme = () => {
    const root = document.documentElement
    const cur = root.getAttribute('data-theme')
    const isDark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
    root.setAttribute('data-theme', isDark ? 'light' : 'dark')
  }

  return (
    <div className="app">
      <TopBar view={view} onView={setView} onToggleTheme={toggleTheme} />
      <Kpis />
      <div className="main">
        {view === 'board' && <BoardView selected={selected} onSelect={setSelected} />}
        {view === 'table' && (
          <TableView
            onOpen={(id) => {
              setSelected(id)
              setView('board')
            }}
          />
        )}
        {view === 'metrics' && <MetricsView />}
      </div>
      <Footer />
    </div>
  )
}
