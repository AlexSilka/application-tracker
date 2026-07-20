import { useQuery } from '@tanstack/react-query'
import { api } from './api'

export function Kpis() {
  const { data: m } = useQuery({ queryKey: ['metrics'], queryFn: api.metrics })
  const f = m?.funnel
  const applied = f?.applied ?? 0
  const stages = f ? [f.applied, f.screening, f.interview, f.offer] : [0, 0, 0, 0]
  const heights = stages.map((v) => (applied ? Math.max(8, Math.round((100 * v) / applied)) : 0))

  return (
    <section className="kpis" aria-label="Сводка">
      <div className="kpi">
        <div className="label">В работе</div>
        <div className="val">{m?.active ?? '—'}</div>
        <div className="foot">активных вакансий</div>
      </div>
      <div className="kpi">
        <div className="label">Всего подано</div>
        <div className="val">{applied}</div>
        <div className="foot">за всё время</div>
      </div>
      <div className="kpi accent">
        <div className="label">Отклик → интервью</div>
        <div className="val">
          {m?.conversions.applied_to_interview ?? 0}
          <small>%</small>
        </div>
        <div className="foot">
          {f?.interview ?? 0} из {applied} · бенчмарк ~3%
        </div>
      </div>
      <div className="kpi">
        <div className="label">Офферы</div>
        <div className="val">{m?.offers ?? 0}</div>
        <div className="foot">активных</div>
      </div>
      <div className="kpi">
        <div className="label">Follow-up</div>
        <div className="val" style={{ color: m?.follow_ups.length ? 'var(--danger)' : undefined }}>
          {m?.follow_ups.length ?? 0}
        </div>
        <div className="foot">на сегодня</div>
      </div>
      <div className="kpi">
        <div className="label">Воронка</div>
        <div className="mini-funnel" aria-hidden>
          {heights.map((h, i) => (
            <i key={i} style={{ height: `${h}%`, opacity: 1 - i * 0.2 }} />
          ))}
        </div>
        <div className="foot mono">
          {f ? `${f.applied} → ${f.screening} → ${f.interview} → ${f.offer}` : ''}
        </div>
      </div>
    </section>
  )
}
