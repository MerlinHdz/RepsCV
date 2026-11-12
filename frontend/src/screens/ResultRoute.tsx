import { useEffect, useState } from 'react'
import { api, type WorkoutResult } from '../api'
import Results from './Results'

type Props = {
  sessionId: number
  initial: WorkoutResult | null
  onDashboard: () => void
  onHistory: () => void
  onNewWorkout: () => void
}

export default function ResultRoute({ sessionId, initial, onDashboard, onHistory, onNewWorkout }: Props) {
  const [result, setResult] = useState<WorkoutResult | null>(initial?.session_id === sessionId ? initial : null)
  const [loading, setLoading] = useState(result === null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (result?.session_id === sessionId) return
    let current = true
    api.status(sessionId).then((response) => {
      if (!current) return
      if (response.status === 'active') throw new Error('This workout is still active.')
      setResult(response as WorkoutResult)
      setLoading(false)
    }).catch((cause) => {
      if (!current) return
      setError(cause instanceof Error ? cause.message : 'Could not load result.')
      setLoading(false)
    })
    return () => { current = false }
  }, [sessionId, attempt, result])

  return <Results result={result?.session_id === sessionId ? result : null} loading={loading} error={error}
    onRetry={() => { setError(null); setLoading(true); setAttempt((value) => value + 1) }}
    onDashboard={onDashboard} onHistory={onHistory} onNewWorkout={onNewWorkout} />
}
