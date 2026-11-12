import type { WorkoutResult } from './api'

export function workoutDate(value: string | null): string {
  if (!value) return 'Date unavailable'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  }).format(new Date(value))
}

export function taiwanWeekLabel(start: string, end: string): string {
  const formatter = new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'Asia/Taipei',
  })
  const lastDay = new Date(new Date(end).getTime() - 24 * 60 * 60 * 1000)
  return `${formatter.format(new Date(start))} – ${formatter.format(lastDay)}`
}

export function workoutTitle(workout: WorkoutResult): string {
  return workout.mode === 'max_set' ? 'Max Set' : 'Normal Workout'
}
