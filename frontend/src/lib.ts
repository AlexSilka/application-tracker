// Small presentation helpers shared across components.

function currencySymbol(cur?: string | null): string {
  if (cur === 'RUB') return '₽'
  if (cur === 'EUR') return '€'
  if (cur === 'USD') return '$'
  return cur || ''
}

function shorten(n: number): string {
  return n >= 1000 && n % 1000 === 0 ? `${n / 1000}k` : n.toLocaleString('en-US')
}

export function formatSalary(a: {
  salary_min?: number | null
  salary_max?: number | null
  currency?: string | null
}): string | null {
  const lo = a.salary_min ?? undefined
  const hi = a.salary_max ?? undefined
  if (lo === undefined && hi === undefined) return null
  const sym = currencySymbol(a.currency)
  const body =
    lo !== undefined && hi !== undefined
      ? lo === hi ? shorten(lo) : `${shorten(lo)}–${shorten(hi)}`
      : shorten((lo ?? hi)!)
  // ₽ trails the number; $/€ lead it.
  return sym === '₽' ? `${body} ${sym}` : `${sym}${body}`
}

export function daysSince(iso: string): number {
  const d = (Date.now() - new Date(iso).getTime()) / 86_400_000
  return Math.max(0, Math.floor(d))
}

/** Whole days from today until `iso` date (negative = overdue). */
export function daysUntil(iso: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(iso)
  target.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
}

/** Compact age for the card's status badge next to the priority dot: 'today' | '6d'. */
export function ageBadge(iso: string): string {
  const d = daysSince(iso)
  return d === 0 ? 'today' : `${d}d`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function fmtDate(iso: string): string {
  const d = new Date(iso)
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  const hasTime = d.getHours() || d.getMinutes()
  const time = hasTime
    ? ` · ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    : ''
  return `${MONTHS[d.getMonth()]} ${d.getDate()}${time}`
}
