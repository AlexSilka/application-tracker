import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
  type DragEndEvent,
} from '@dnd-kit/core'
import { api, type Application, type Status } from './api'
import { KIND_LABEL, SRC_COLOR, STATUS_LABEL, WORK_MODE_LABEL } from './constants'
import { avatarColor, daysUntil, fmtDate, fmtDateTime, formatSalary, initials, stageAge } from './lib'
import { IconCheck, IconClock, IconClose, IconDoc, IconLines } from './icons'

export function Stars({ n }: { n: number }) {
  return (
    <span className="stars">
      {'★'.repeat(n)}
      <span className="off">{'★'.repeat(5 - n)}</span>
    </span>
  )
}

function NextPill({ app }: { app: Application }) {
  if (!app.next_action && !app.next_action_date) return <span className="age">—</span>
  let cls = 'next'
  let text = app.next_action ?? 'follow-up'
  if (app.next_action_date) {
    const d = daysUntil(app.next_action_date)
    if (d < 0) {
      cls = 'next overdue'
      text = `просрочен ${-d}д`
    } else if (d <= 2) {
      cls = 'next soon'
      text = `${text} · ${d === 0 ? 'сегодня' : d + 'д'}`
    }
  }
  return <span className={cls}>{text}</span>
}

function Card({
  app,
  selected,
  onSelect,
}: {
  app: Application
  selected: boolean
  onSelect: (id: number) => void
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: app.id })
  const style: CSSProperties = {}
  if (transform) {
    style.transform = `translate3d(${transform.x}px, ${transform.y}px, 0)`
    style.zIndex = 50
  }
  if (isDragging) style.opacity = 0.55
  const salary = formatSalary(app)
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      style={style}
      className={`card ${selected ? 'sel' : ''}`}
      onClick={() => onSelect(app.id)}
    >
      <div className="card-top">
        <div className="avatar" style={{ background: avatarColor(app.company) }}>
          {initials(app.company)}
        </div>
        <div className="card-co">{app.company}</div>
      </div>
      <div className="card-title">{app.title}</div>
      <div className="card-meta">
        <span className="chip">
          <span className="cdot" style={{ background: SRC_COLOR[app.source] ?? 'var(--st-saved)' }} />
          {app.source}
        </span>
        {salary && <span className="chip salary">{salary}</span>}
        <Stars n={app.priority} />
      </div>
      <div className="card-foot">
        <span className="age">{app.applied_at ? stageAge(app.updated_at) : 'не подано'}</span>
        <NextPill app={app} />
      </div>
    </div>
  )
}

function Column({
  status,
  items,
  selected,
  onSelect,
}: {
  status: Status
  items: Application[]
  selected: number | null
  onSelect: (id: number) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  return (
    <div className="col">
      <div className="col-head">
        <span className="dot" style={{ background: `var(--st-${status})` }} />
        <span className="name">{STATUS_LABEL[status]}</span>
        <span className="count">{items.length}</span>
      </div>
      <div ref={setNodeRef} className={`col-body ${isOver ? 'over' : ''}`}>
        {items.map((a) => (
          <Card key={a.id} app={a} selected={selected === a.id} onSelect={onSelect} />
        ))}
      </div>
    </div>
  )
}

function ArchiveColumn({ items }: { items: Application[] }) {
  const counts: Record<string, number> = {}
  for (const a of items) counts[a.status] = (counts[a.status] ?? 0) + 1
  return (
    <div className="col">
      <div className="col-head">
        <span className="dot" style={{ background: 'var(--st-ghosted)' }} />
        <span className="name">Архив</span>
        <span className="count">{items.length}</span>
      </div>
      <div className="col-body">
        <div className="col-archived-box">
          <b>{items.length}</b> закрытых вакансий
          <div className="row">
            {Object.entries(counts).map(([s, n]) => (
              <span key={s} className="chip">
                <span className="cdot" style={{ background: `var(--st-${s})` }} />
                {STATUS_LABEL[s as Status]} {n}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function BoardView({
  selected,
  onSelect,
}: {
  selected: number | null
  onSelect: (id: number | null) => void
}) {
  const qc = useQueryClient()
  const { data: meta } = useQuery({ queryKey: ['meta'], queryFn: api.meta })
  const { data: apps } = useQuery({ queryKey: ['apps'], queryFn: api.list })
  const mutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: Status }) => api.changeStatus(id, status),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['apps'] })
      qc.invalidateQueries({ queryKey: ['metrics'] })
      qc.invalidateQueries({ queryKey: ['app', vars.id] })
    },
  })
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  if (!meta || !apps) return <div className="board-wrap"><div className="loading">Загрузка…</div></div>

  const active = meta.active_statuses
  const terminalSet = new Set<string>(meta.terminal_statuses)
  const terminal = apps.filter((a) => terminalSet.has(a.status))

  function onDragEnd(e: DragEndEvent) {
    const overId = e.over?.id as Status | undefined
    if (!overId || !active.includes(overId)) return
    const id = Number(e.active.id)
    const app = apps!.find((a) => a.id === id)
    if (app && app.status !== overId) mutation.mutate({ id, status: overId })
  }

  return (
    <>
      <div className="board-wrap">
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="board">
            {active.map((s) => (
              <Column
                key={s}
                status={s}
                items={apps.filter((a) => a.status === s)}
                selected={selected}
                onSelect={onSelect}
              />
            ))}
            <ArchiveColumn items={terminal} />
          </div>
        </DndContext>
      </div>
      {selected != null && (
        <>
          <DetailDrawer id={selected} onClose={() => onSelect(null)} />
          <div className="scrim show" onClick={() => onSelect(null)} />
        </>
      )}
    </>
  )
}

function TimelineNode({ meta, first }: { meta?: Record<string, unknown> | null; first: boolean }) {
  const to = meta && typeof meta.to === 'string' ? (meta.to as string) : null
  const style: CSSProperties | undefined = !first && to ? { background: `var(--st-${to})` } : undefined
  return <div className={`tl-node ${first ? 'accent' : ''}`} style={style} />
}

function DetailDrawer({ id, onClose }: { id: number; onClose: () => void }) {
  const { data: app } = useQuery({ queryKey: ['app', id], queryFn: () => api.get(id) })
  if (!app) return <aside className="drawer"><div className="loading">Загрузка…</div></aside>

  const salary = formatSalary(app)
  const sub = [app.location, app.work_mode ? WORK_MODE_LABEL[app.work_mode] ?? app.work_mode : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <aside className="drawer" aria-label="Карточка вакансии">
      <div className="drawer-head">
        <div className="drawer-top">
          <div className="avatar" style={{ background: avatarColor(app.company) }}>
            {initials(app.company)}
          </div>
          <div>
            <div className="drawer-title">{app.title}</div>
            <div className="drawer-co">{app.company}{sub ? ` · ${sub}` : ''}</div>
          </div>
          <button className="icon-btn drawer-close" aria-label="Закрыть" onClick={onClose}>
            <IconClose />
          </button>
        </div>
        <span className="status-pill" style={{ background: `var(--st-${app.status})` }}>
          <IconCheck /> {STATUS_LABEL[app.status]}
        </span>
        <div className="drawer-facts">
          {salary && <span className="chip salary">{salary}</span>}
          <span className="chip">
            <span className="cdot" style={{ background: SRC_COLOR[app.source] ?? 'var(--st-saved)' }} />
            {app.source}
          </span>
          <span className="chip"><Stars n={app.priority} /></span>
        </div>
      </div>

      <div className="drawer-body">
        {app.next_action && (
          <div className="next-banner">
            <span className="ico"><IconClock /></span>
            <div>
              Дальше: <b>{app.next_action}</b>
              {app.next_action_date ? ` — ${fmtDate(app.next_action_date)}` : ''}
            </div>
          </div>
        )}

        <div>
          <div className="sect-label"><IconLines /> Вакансия</div>
          {app.description ? (
            <p className="jd">{app.description}</p>
          ) : (
            <p className="jd empty">Описание не сохранено</p>
          )}
          {app.job_url && (
            <p style={{ marginTop: 8 }}>
              <a href={app.job_url} target="_blank" rel="noreferrer"
                 style={{ color: 'var(--accent)', fontSize: 13, textDecoration: 'none' }}>
                Открыть вакансию ↗
              </a>
            </p>
          )}
        </div>

        <div>
          <div className="sect-label">Что отправили</div>
          {app.resume_version ? (
            <div className="doc-line">
              <IconDoc />
              <span className="fname">{app.resume_version}</span>
              <span className="tag">резюме</span>
            </div>
          ) : (
            <p className="jd empty">Резюме не указано</p>
          )}
          {app.cover_letter && <p className="cover">«{app.cover_letter}»</p>}
        </div>

        {(app.contact_name || app.contact_email) && (
          <div>
            <div className="sect-label">Контакт</div>
            <div className="contact">
              <div className="avatar">{initials(app.contact_name ?? '—')}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{app.contact_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  {app.contact_email}
                  {app.contact_url && (
                    <> · <a href={app.contact_url} target="_blank" rel="noreferrer"
                            style={{ color: 'var(--accent)', textDecoration: 'none' }}>LinkedIn ↗</a></>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <div>
          <div className="sect-label">Таймлайн</div>
          <div className="timeline">
            {app.events.map((e, i) => (
              <div className="tl" key={e.id}>
                <div className="tl-rail">
                  <TimelineNode meta={e.meta} first={i === 0} />
                  <div className="tl-line" />
                </div>
                <div className="tl-body">
                  <div className="tl-when">{fmtDateTime(e.occurred_at)}</div>
                  <div className="tl-kind">{KIND_LABEL[e.kind] ?? e.kind}</div>
                  {e.body && <div className="tl-text">{e.body}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="drawer-actions">
        <button className="primary">Сменить статус</button>
        <button>Заметка</button>
        {app.job_url && <button onClick={() => window.open(app.job_url!, '_blank')}>Открыть ↗</button>}
      </div>
    </aside>
  )
}
