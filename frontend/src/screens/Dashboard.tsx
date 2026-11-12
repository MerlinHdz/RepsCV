import { api, type ActiveWorkout, type User } from '../api'
import WorkoutItem from '../components/WorkoutItem'
import { taiwanWeekLabel } from '../format'
import { useResource } from '../useResource'

type Props = {
  user: User
  activeWorkout: ActiveWorkout | null
  onStart: () => void
  onHistory: () => void
  onResume: () => void
  onOpenWorkout: (id: number) => void
}

export default function Dashboard({ user, activeWorkout, onStart, onHistory, onResume, onOpenWorkout }: Props) {
  const { data, loading, error, retry } = useResource(api.dashboard)
  const weekShare = data && data.lifetime_xp > 0 ? Math.round(data.weekly_xp / data.lifetime_xp * 100) : 0

  return (
    <div className="screen dashboard-screen">
      <div className="screen-heading">
        <p className="eyebrow">Your training ground</p>
        <h1>Keep the<br /><em>momentum.</em></h1>
        <p>Welcome back, <strong>{user.username}</strong>. Your next session is one tap away.</p>
      </div>

      {activeWorkout && <div className="active-banner">
        <span className="live-dot" aria-hidden="true" />
        <div><strong>{activeWorkout.mode === 'normal' ? 'Normal Workout in progress' : 'Max Set in progress'}</strong><small>{activeWorkout.rep_count} saved reps · Resume tracking</small></div>
        <button type="button" onClick={onResume}>Resume</button>
      </div>}

      <button className="start-hero" type="button" onClick={activeWorkout ? onResume : onStart}>
        <span className="start-hero-top">PUSH-UPS · LIVE TRACKING</span>
        <span className="start-hero-main">{activeWorkout ? 'Resume workout' : 'Start workout'} <span aria-hidden="true">↗</span></span>
        <span className="start-hero-foot">{activeWorkout ? 'Pick up your active session' : 'Show up. Do the work. Own the result.'}</span>
      </button>

      {loading && <div className="loading-card" role="status">Loading your stats…</div>}
      {error && <div className="error-card" role="alert"><p>Could not load your dashboard: {error}</p><button type="button" onClick={retry}>Try again</button></div>}
      {data && <>
        <div className="section-heading"><div><p className="eyebrow">The numbers</p><h2>Your progress</h2></div></div>
        <div className="stat-grid">
          <div className="stat-card stat-card-primary"><span>Lifetime XP</span><strong>{data.lifetime_xp.toLocaleString()}</strong><small>earned from finished workouts</small></div>
          <div className="stat-card"><span>This week</span><strong>{data.weekly_xp.toLocaleString()} <small>XP</small></strong><small>{taiwanWeekLabel(data.week_start, data.week_end)} · Taipei</small></div>
          <div className="stat-card"><span>Total push-ups</span><strong>{data.total_pushups.toLocaleString()}</strong><small>valid reps on record</small></div>
          <div className="stat-card"><span>Max Set PB</span><strong>{data.max_set_personal_best ?? '—'}</strong><small>{data.max_set_personal_best === null ? 'Your first Max Set is waiting' : 'most reps in one set'}</small></div>
        </div>
        <div className="weekly-strip">
          <div><strong>{data.weekly_xp.toLocaleString()} XP</strong><span>earned this Taiwan week</span></div>
          <div className="weekly-track" role="img" aria-label={`${weekShare}% of your lifetime XP was earned this week`}><span style={{ width: `${weekShare}%` }} /></div>
          <small>{data.lifetime_xp === 0 ? 'Complete a workout to start building your record.' : `${weekShare}% of your lifetime XP`}</small>
        </div>
        <div className="section-heading"><div><p className="eyebrow">The work so far</p><h2>Recent sessions</h2></div><button className="text-action" type="button" onClick={onHistory}>View all ↗</button></div>
        {data.recent_workouts.length === 0
          ? <div className="empty-card"><span aria-hidden="true">◎</span><strong>No sessions yet</strong><p>Your first finished workout will show up here.</p></div>
          : <div className="workout-list">{data.recent_workouts.map((workout) => <WorkoutItem key={workout.session_id} workout={workout} onOpen={onOpenWorkout} />)}</div>}
      </>}
    </div>
  )
}
