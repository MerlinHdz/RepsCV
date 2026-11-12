import type { WorkoutResult } from '../api'
import { workoutDate, workoutTitle } from '../format'
import { formatDuration } from '../sessionUi'

type Props = {
  result: WorkoutResult | null
  loading: boolean
  error: string | null
  onRetry: () => void
  onDashboard: () => void
  onHistory: () => void
  onNewWorkout: () => void
}

export default function Results({ result, loading, error, onRetry, onDashboard, onHistory, onNewWorkout }: Props) {
  if (loading) return <div className="screen"><div className="loading-card" role="status">Loading your result…</div></div>
  if (error) return <div className="screen"><div className="error-card" role="alert"><p>Could not load your result: {error}</p><button type="button" onClick={onRetry}>Try again</button></div></div>
  if (!result) return null
  const completed = result.status === 'completed'
  return (
    <div className="screen results-screen">
      <div className="result-hero">
        <p className="eyebrow">Session complete · RepsCV</p>
        <div className="result-emblem" aria-hidden="true">{completed ? '✓' : '!'}</div>
        <h1>{completed ? <>Work<br /><em>done.</em></> : <>Set<br /><em>interrupted.</em></>}</h1>
        <p>{completed ? 'Every valid rep is on the record.' : 'Tracking was interrupted. This attempt earned no XP or personal best.'}</p>
      </div>
      {result.new_personal_best && <div className="pb-banner">✦ New Max Set personal best</div>}
      <div className="result-stats">
        <div><span>Valid reps</span><strong>{result.rep_count}</strong></div>
        <div><span>XP earned</span><strong>{result.xp_earned}</strong></div>
        <div><span>Duration</span><strong>{formatDuration(result.duration_ms)}</strong></div>
      </div>
      <div className="result-meta"><span>{workoutTitle(result)}</span><span>{completed ? 'Completed' : 'Interrupted'}</span>{result.completed_at && <span>{workoutDate(result.completed_at)}</span>}</div>
      <div className="result-actions"><button type="button" onClick={onDashboard}>Back to dashboard <span aria-hidden="true">↗</span></button><button type="button" className="button-outline" onClick={onHistory}>View history</button><button type="button" className="button-ghost" onClick={onNewWorkout}>Start another workout</button></div>
    </div>
  )
}
