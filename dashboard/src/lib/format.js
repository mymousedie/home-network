export function timeAgo(ts) {
  if (ts == null) return 'never'
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

export function duration(seconds) {
  if (seconds == null) return '–'
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h) return `${h}h ${m}m`
  if (m) return `${m}m ${s % 60}s`
  return `${s}s`
}

export function ms(v) {
  if (v == null) return '–'
  return v < 10 ? `${v.toFixed(1)} ms` : `${Math.round(v)} ms`
}

export function pct(v) {
  return v == null ? '–' : `${Math.round(v)}%`
}

export function num(v) {
  return v == null ? '–' : v.toLocaleString()
}

export function clock(ts, withDate = false) {
  if (ts == null) return '–'
  return new Date(ts * 1000).toLocaleString([], {
    ...(withDate ? { month: 'short', day: 'numeric' } : {}),
    hour: '2-digit',
    minute: '2-digit',
    second: withDate ? undefined : '2-digit',
  })
}

/** Axis tick label for a bucket timestamp, coarser for longer ranges. */
export function tick(ts, hours) {
  const d = new Date(ts * 1000)
  if (hours > 24) return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export const RANGES = [
  { value: '1', label: 'Last hour' },
  { value: '6', label: 'Last 6 hours' },
  { value: '24', label: 'Last 24 hours' },
  { value: '168', label: 'Last 7 days' },
]
