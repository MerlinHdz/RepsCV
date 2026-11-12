import { api } from '../api'
import WorkoutItem from '../components/WorkoutItem'
import { useResource } from '../useResource'

type Props = { onStart: () => void; onOpenWorkout: (id: number) => void }

export default function History({ onStart, onOpenWorkout }: Props) {
  const { data, loading, error, retry } = useResource(api.history)
  return (
    <div className="screen">
      <div className="screen-heading"><p className="eyebrow">The training log</p><h1>Every rep<br /><em>counts.</em></h1><p>Your completed push-up workouts, newest first. Times use your device’s timezone.</p></div>
      {loading && <div className="loading-card" role="status">Loading workout history…</div>}
      {error && <div className="error-card" role="alert"><p>Could not load history: {error}</p><button type="button" onClick={retry}>Try again</button></div>}
      {data && <>
        <div className="section-heading"><h2>{data.length} completed {data.length === 1 ? 'session' : 'sessions'}</h2></div>
        {data.length === 0
          ? <div className="empty-card"><span aria-hidden="true">↗</span><strong>No workouts recorded</strong><p>Finish a workout and your results will live here.</p><button type="button" onClick={onStart}>Start a workout</button></div>
          : <div className="workout-list">{data.map((workout) => <WorkoutItem key={workout.session_id} workout={workout} onOpen={onOpenWorkout} />)}</div>}
      </>}
    </div>
  )
}
