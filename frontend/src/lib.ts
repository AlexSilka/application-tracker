// Small presentation helpers shared across components.

const PALETTE = [
  '#2A6FF0', '#00C56E', '#E0A400', '#7B5CE0', '#FF6C37',
  '#EC2027', '#1F8AF0', '#7A48D6', '#0EA5B7', '#E0498B',
]

export function avatarColor(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  const s = parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)
  return s.toUpperCase()
}

function currencySymbol(cur?: string | null): string {
  if (cur === 'RUB') return '₽'
  if (cur === 'EUR') return '€'
  if (cur === 'USD') return '$'
  return cur || ''
}

function shorten(n: number): string {
  return n >= 1000 && n % 1000 === 0 ? `${n / 1000}k` : n.toLocaleString('ru-RU')
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

export function stageAge(iso: string): string {
  const d = daysSince(iso)
  if (d === 0) return 'сегодня'
  return `в стадии ${d}д`
}

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

export function fmtDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`
}

export function fmtDateTime(iso: string): string {
  const d = new Date(iso)
  const hasTime = d.getHours() || d.getMinutes()
  const time = hasTime
    ? ` · ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    : ''
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${time}`
}
