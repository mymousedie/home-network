import { useCallback, useEffect, useRef, useState } from 'react'

export const POLL_MS = 15000

export async function apiGet(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString()
  const res = await fetch(`/api${path}${qs ? `?${qs}` : ''}`)
  if (!res.ok) throw new Error(await errorText(res))
  return res.json()
}

export async function apiPost(path) {
  const res = await fetch(`/api${path}`, { method: 'POST' })
  if (!res.ok) throw new Error(await errorText(res))
  return res.json()
}

async function errorText(res) {
  try {
    const body = await res.json()
    return body.detail || `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

/** Fetch `path` now, whenever params change, and every `intervalMs`. */
export function usePoll(path, params = {}, intervalMs = POLL_MS) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const key = JSON.stringify(params)
  const seq = useRef(0)

  const load = useCallback(async () => {
    const mine = ++seq.current
    try {
      const d = await apiGet(path, JSON.parse(key))
      if (mine === seq.current) {
        setData(d)
        setError(null)
      }
    } catch (e) {
      if (mine === seq.current) setError(e.message)
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [path, key])

  useEffect(() => {
    load()
    if (!intervalMs) return undefined
    const t = setInterval(load, intervalMs)
    return () => clearInterval(t)
  }, [load, intervalMs])

  return { data, error, loading, reload: load }
}
