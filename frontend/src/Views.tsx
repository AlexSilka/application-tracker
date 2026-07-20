import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { STATUS_LABEL } from './constants'
import { avatarColor, daysSince, formatSalary, initials } from './lib'
import { Stars } from './Board'

export function TableView({ onOpen }: { onOpen: (id: number) => void }) {
  const { data: apps } = useQuery({ queryKey: ['apps'], queryFn: api.list })
  if (!apps) return <div className="loading">Загрузка…</div>
  return (
    <div className="table-scroll">
      <table className="apps">
        <thead>
          <tr>
            <th>Компания / роль</th>
            <th>Статус</th>
            <th>Канал</th>
            <th>Приоритет</th>
            <th>Зарплата</th>
            <th>Обновлено</th>
            <th>Next action</th>
          </tr>
        </thead>
        <tbody>
          {apps.map((a) => (
            <tr key={a.id} onClick={() => onOpen(a.id)}>
              <td>
                <div className="t-co">
                  <div className="avatar" style={{ background: avatarColor(a.company) }}>
                    {initials(a.company)}
                  </div>
                  <div>
                    <div className="t-title">{a.title}</div>
                    <div className="t-sub">{a.company}</div>
                  </div>
                </div>
              </td>
              <td>
                <span className="s-tag">
                  <span className="dot" style={{ background: `var(--st-${a.status})` }} />
                  {STATUS_LABEL[a.status]}
                </span>
              </td>
              <td>{a.source}</td>
              <td><Stars n={a.priority} /></td>
              <td className="t-num">{formatSalary(a) ?? '—'}</td>
              <td className="t-num">{daysSince(a.updated_at)}д</td>
              <td>{a.next_action ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FunnelRow({ label, value, width, color }: { label: string; value: number; width: number; color: string }) {
  return (
    <div className="funnel-row">
      <span className="fl">{label}</span>
      <div className="funnel-bar" style={{ width: `${width}%`, background: color }}>{value}</div>
      <span className="fp">{width}%</span>
    </div>
  )
}

function Conv({ label, note, value, color }: { label: string; note: string; value: string; color: string }) {
  return (
    <div className="conv">
      <div>
        <div className="cl">{label}</div>
        <div className="cn">{note}</div>
      </div>
      <div className="cv" style={{ color }}>{value}</div>
    </div>
  )
}

export function MetricsView() {
  const { data: m } = useQuery({ queryKey: ['metrics'], queryFn: api.metrics })
  if (!m) return <div className="loading">Загрузка…</div>
  const f = m.funnel
  const base = f.applied || 1
  const pct = (v: number) => Math.round((100 * v) / base)

  return (
    <div className="metrics">
      <div className="m-grid">
        <div className="panel">
          <h3>Воронка</h3>
          <p className="hint">Сколько откликов доходит до каждой стадии</p>
          <div className="funnel">
            <FunnelRow label="Подано" value={f.applied} width={100} color="var(--accent)" />
            <FunnelRow label="Скрининг" value={f.screening} width={pct(f.screening)} color="var(--st-screening)" />
            <FunnelRow label="Интервью" value={f.interview} width={pct(f.interview)} color="var(--st-interview)" />
            <FunnelRow label="Оффер" value={f.offer} width={pct(f.offer)} color="var(--st-offer)" />
          </div>
        </div>

        <div className="panel">
          <h3>Конверсии</h3>
          <p className="hint">Ключевые переходы</p>
          <div className="conv-tiles">
            <Conv label="Отклик → интервью" note={`${f.interview} / ${f.applied}`}
                  value={`${m.conversions.applied_to_interview}%`} color="var(--st-interview)" />
            <Conv label="Интервью → оффер" note={`${f.offer} / ${f.interview}`}
                  value={`${m.conversions.interview_to_offer}%`} color="var(--st-offer)" />
            <Conv label="Response rate" note="дошли дальше отклика"
                  value={`${m.conversions.response_rate}%`} color="var(--good)" />
          </div>
        </div>

        <div className="panel">
          <h3>По каналам</h3>
          <p className="hint">Где отклики реально конвертируются в интервью</p>
          <div className="chan">
            {m.by_channel.map((c) => (
              <div className="chan-row" key={c.source}>
                <span>{c.source}</span>
                <div className="chan-track">
                  <div className="chan-fill"
                       style={{ width: `${c.rate}%`, background: c.rate > 0 ? 'var(--st-accepted)' : 'var(--accent)' }} />
                </div>
                <span className="chan-val">{c.interview}/{c.applied} · {c.rate}%</span>
              </div>
            ))}
            {!m.by_channel.length && <p className="empty">Пока нет данных</p>}
          </div>
        </div>

        <div className="panel">
          <h3>Follow-up на сегодня</h3>
          <p className="hint">Не потерять инициативу</p>
          <div className="followups">
            {m.follow_ups.map((fu) => (
              <div className="fu" key={fu.id}>
                <div className="avatar" style={{ background: avatarColor(fu.company) }}>
                  {initials(fu.company)}
                </div>
                <div>
                  <div className="fu-main">{fu.company} · {fu.title}</div>
                  <div className="fu-sub">{fu.next_action ?? ''}</div>
                </div>
                <span className={`fu-badge ${fu.overdue_days > 0 ? 'over' : 'today'}`}>
                  {fu.overdue_days > 0 ? `просрочен ${fu.overdue_days}д` : 'сегодня'}
                </span>
              </div>
            ))}
            {!m.follow_ups.length && <p className="empty">Нет задач на сегодня 👌</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
