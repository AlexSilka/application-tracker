import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { STATUS_LABEL } from './constants'
import { daysSince, formatSalary } from './lib'

export function TableView({ onOpen }: { onOpen: (id: number) => void }) {
  const { data: apps } = useQuery({ queryKey: ['apps'], queryFn: api.list })
  if (!apps) return <div className="loading">Loading…</div>
  return (
    <div className="table-scroll">
      <table className="apps">
        <thead>
          <tr>
            <th>Company / role</th>
            <th>Status</th>
            <th>Channel</th>
            <th>Salary</th>
            <th>Applied</th>
            <th>Next action</th>
          </tr>
        </thead>
        <tbody>
          {apps.map((a) => (
            <tr key={a.id} onClick={() => onOpen(a.id)}>
              <td>
                <div className="t-co">
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
              <td>{a.applied_via}</td>
              <td className="t-num">{formatSalary(a) ?? '—'}</td>
              <td className="t-num">{a.applied_at ? `${daysSince(a.applied_at)}d` : '—'}</td>
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
  if (!m) return <div className="loading">Loading…</div>
  const f = m.funnel
  const base = f.applied || 1
  const pct = (v: number) => Math.round((100 * v) / base)
  const respToInterview = f.screening ? Math.round((100 * f.interview) / f.screening) : 0

  return (
    <div className="metrics">
      <div className="m-grid">
        <div className="panel">
          <h3>Funnel</h3>
          <p className="hint">How many applications reach each stage</p>
          <div className="funnel">
            <FunnelRow label="Applied" value={f.applied} width={100} color="var(--accent)" />
            <FunnelRow label="In Contact" value={f.screening} width={pct(f.screening)} color="var(--st-screening)" />
            <FunnelRow label="Interview" value={f.interview} width={pct(f.interview)} color="var(--st-interview)" />
            <FunnelRow label="Offer" value={f.offer} width={pct(f.offer)} color="var(--st-offer)" />
          </div>
        </div>

        <div className="panel">
          <h3>Conversions</h3>
          <p className="hint">Key transitions</p>
          <div className="conv-tiles">
            <Conv label="Applied → Response" note={`${f.screening} / ${f.applied}`}
                  value={`${m.conversions.response_rate}%`} color="var(--good)" />
            <Conv label="Response → Interview" note={`${f.interview} / ${f.screening}`}
                  value={`${respToInterview}%`} color="var(--st-interview)" />
            <Conv label="Interview → Offer" note={`${f.offer} / ${f.interview}`}
                  value={`${m.conversions.interview_to_offer}%`} color="var(--st-offer)" />
          </div>
        </div>

        <div className="panel" style={{ gridColumn: '1 / -1' }}>
          <h3>By channel</h3>
          <p className="hint">Which channels actually get a response</p>
          <div className="chan">
            {m.by_channel.map((c) => (
              <div className="chan-row" key={c.applied_via}>
                <span>{c.applied_via}</span>
                <div className="chan-track">
                  <div className="chan-fill"
                       style={{ width: `${c.rate}%`, background: c.rate > 0 ? 'var(--st-accepted)' : 'var(--accent)' }} />
                </div>
                <span className="chan-val">{c.interview}/{c.applied} · {c.rate}%</span>
              </div>
            ))}
            {!m.by_channel.length && <p className="empty">No data yet</p>}
          </div>
        </div>
      </div>
    </div>
  )
}
