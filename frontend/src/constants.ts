import type { Status } from './api'

export const STATUS_LABEL: Record<Status, string> = {
  saved: 'Saved',
  applied: 'Applied',
  screening: 'In Contact',
  interview: 'Interview',
  offer: 'Offer',
  accepted: 'Accepted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  ghosted: 'Ghosted',
}

export const WORK_MODE_LABEL: Record<string, string> = {
  onsite: 'onsite',
  hybrid: 'hybrid',
  remote: 'remote',
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
  aggregator: 'var(--st-ghosted)',
  google: 'var(--st-screening)',
}

export const KIND_LABEL: Record<string, string> = {
  created: 'Created',
  status_change: 'Status',
  note: 'Note',
  follow_up: 'Follow-up',
  interview: 'Interview',
  email_sent: 'Email',
  offer: 'Offer',
  rejection: 'Rejection',
}
