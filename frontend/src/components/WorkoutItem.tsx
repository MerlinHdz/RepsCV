import type { WorkoutResult } from '../api'
import { workoutDate, workoutTitle } from '../format'
import { formatDuration } from '../sessionUi'

type Props = { workout: WorkoutResult; onOpen: (sessionId: number) => void }

export default function WorkoutItem({ workout, onOpen }: Props) {
  return (
    <button className="workout-item" type="button" onClick={() => onOpen(workout.session_id)}
      aria-label={`View ${workoutTitle(workout)} from ${workoutDate(workout.completed_at)}`}>
      <span className="workout-item-icon" aria-hidden="true">↗</span>
      <span className="workout-item-main">
        <strong>{workoutTitle(workout)} {workout.new_personal_best && <span className="mini-badge">New PB</span>}</strong>
        <small>{workoutDate(workout.completed_at)} · {formatDuration(workout.duration_ms)}</small>
      </span>
      <span className="workout-item-numbers"><strong>{workout.rep_count} <small>reps</small></strong><small>+{workout.xp_earned} XP</small></span>
    </button>
  )
}
