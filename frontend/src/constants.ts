import type { Status } from './api'

export const STATUS_LABEL: Record<Status, string> = {
  saved: 'Сохранено',
  applied: 'Отклик',
  screening: 'Скрининг',
  interview: 'Интервью',
  offer: 'Оффер',
  accepted: 'Принят',
  rejected: 'Отказ',
  withdrawn: 'Снят',
  ghosted: 'Тишина',
}

export const WORK_MODE_LABEL: Record<string, string> = {
  onsite: 'офис',
  hybrid: 'гибрид',
  remote: 'удалёнка',
}

// Subtle colour cue per channel (distinct from status hues).
export const SRC_COLOR: Record<string, string> = {
  linkedin: 'var(--st-applied)',
  'hh.ru': 'var(--st-rejected)',
  referral: 'var(--st-accepted)',
  'company site': 'var(--st-saved)',
  telegram: 'var(--st-screening)',
  indeed: 'var(--st-interview)',
  recruiter: 'var(--st-offer)',
  email: 'var(--st-withdrawn)',
}

export const KIND_LABEL: Record<string, string> = {
  created: 'Добавлено',
  status_change: 'Статус',
  note: 'Заметка',
  follow_up: 'Follow-up',
  interview: 'Интервью',
  email_sent: 'Письмо',
  offer: 'Оффер',
  rejection: 'Отказ',
}
