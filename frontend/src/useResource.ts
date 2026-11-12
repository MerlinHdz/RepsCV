import { useEffect, useState } from 'react'

type Resource<T> = { data: T | null; loading: boolean; error: string | null; retry: () => void }

export function useResource<T>(load: () => Promise<T>): Resource<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let current = true
    load().then((value) => {
      if (!current) return
      setData(value)
      setLoading(false)
      setError(null)
    }).catch((cause) => {
      if (!current) return
      setError(cause instanceof Error ? cause.message : 'Could not load data.')
      setLoading(false)
    })
    return () => { current = false }
  }, [load, attempt])

  return { data, loading, error, retry: () => {
    setLoading(true)
    setError(null)
    setAttempt((value) => value + 1)
  } }
}
