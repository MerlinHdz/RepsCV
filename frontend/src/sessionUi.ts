import type { Mode, WorkoutResult } from './api'

export function endLabel(mode: Mode) { return mode === 'normal' ? 'Finish workout' : 'End Max Set' }
export function modeLabel(mode: Mode) { return mode === 'normal' ? 'Normal Workout' : 'Max Set' }
export function resultLabel(result: WorkoutResult) {
  return result.status === 'interrupted' ? 'Interrupted — no XP or personal best' : 'Workout completed'
}
export function formatDuration(ms: number | null) {
  if (ms === null) return '—'
  const seconds = Math.floor(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
