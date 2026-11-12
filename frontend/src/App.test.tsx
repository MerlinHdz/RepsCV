import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { api, type WorkoutResult } from './api'

vi.mock('./api', () => ({ api: {
  me: vi.fn(), register: vi.fn(), login: vi.fn(), logout: vi.fn(),
  history: vi.fn(), profile: vi.fn(), status: vi.fn(), dashboard: vi.fn(), leaderboard: vi.fn(),
} }))

vi.mock('./PoseDetector', () => ({ default: ({ mode, resume, onSessionStarted, onResult }: {
  mode: string; resume?: { id: number }; onSessionStarted: (session: { id: number; mode: 'normal' | 'max_set'; rep_count: number; status: string; started_at: string }) => void
  onResult: (result: WorkoutResult) => void
}) => <div>
  <p>Camera mode: {mode}</p>
  {resume && <p>Resume workout: {resume.id}</p>}
  <button onClick={() => onSessionStarted({ id: 1, mode: mode as 'normal' | 'max_set', rep_count: 0, status: 'active', started_at: '2026-11-11T00:00:00Z' })}>Mock start</button>
  <button onClick={() => onResult({ type: 'workout_result', session_id: 1,
    mode: mode as WorkoutResult['mode'], status: 'completed', rep_count: 3,
    duration_ms: 65000, xp_earned: 30, new_personal_best: true,
    completed_at: '2026-11-11T00:00:00Z' })}>Mock finish</button>
  <button onClick={() => onResult({ type: 'workout_result', session_id: 1,
    mode: mode as WorkoutResult['mode'], status: 'interrupted', rep_count: 3,
    duration_ms: 65000, xp_earned: 0, new_personal_best: false,
    completed_at: null })}>Mock interruption</button>
</div> }))

const user = { id: 1, username: 'student', department: null, csrf_token: 'csrf', active_workout: null }
const result: WorkoutResult = { type: 'workout_result', session_id: 7, mode: 'max_set', status: 'completed',
  rep_count: 3, duration_ms: 65000, xp_earned: 30, new_personal_best: true, completed_at: '2026-11-11T00:00:00Z' }
const dashboard = { username: 'student', lifetime_xp: 30, weekly_xp: 30, total_pushups: 3,
  max_set_personal_best: 3, recent_workouts: [result], week_start: '2026-11-08T16:00:00Z',
  week_end: '2026-11-15T16:00:00Z', timezone: 'Asia/Taipei' as const }
const leaderboard = { period: 'weekly' as const, week_start: dashboard.week_start,
  week_end: dashboard.week_end, timezone: 'Asia/Taipei' as const, current_user_rank: 1,
  entries: [{ rank: 1, user_id: 1, username: 'student', weekly_xp: 30, is_current_user: true },
    { rank: 1, user_id: 2, username: 'peer', weekly_xp: 30, is_current_user: false }] }

beforeEach(() => {
  vi.resetAllMocks()
  window.history.replaceState({}, '', '/')
  sessionStorage.clear()
  vi.mocked(api.me).mockResolvedValue(user)
  vi.mocked(api.dashboard).mockResolvedValue(dashboard)
  vi.mocked(api.history).mockResolvedValue([result])
  vi.mocked(api.leaderboard).mockResolvedValue(leaderboard)
  vi.mocked(api.status).mockResolvedValue(result)
  vi.mocked(api.profile).mockResolvedValue(user)
  vi.mocked(api.logout).mockResolvedValue(undefined)
})

afterEach(cleanup)

test('registers, reaches dashboard, and opens the camera from workout mode selection', async () => {
  vi.mocked(api.me).mockRejectedValueOnce(new Error('Login required')).mockResolvedValue(user)
  vi.mocked(api.register).mockResolvedValue(user)
  render(<App />)
  fireEvent.click(await screen.findByText(/Create an account/))
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'student' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
  fireEvent.click(screen.getByRole('button', { name: /Create account/ }))
  await screen.findByText('Your progress')
  fireEvent.click(screen.getByRole('button', { name: /Start workout/ }))
  fireEvent.click(screen.getByRole('button', { name: /Normal/ }))
  expect(screen.getByText('Camera mode: normal')).toBeTruthy()
})

test('dashboard, history, leaderboard, and profile show persisted data', async () => {
  render(<App />)
  await screen.findByText('Your progress')
  expect(screen.getByText('Recent sessions')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  await screen.findByText('1 completed session')
  expect(screen.getByText('Max Set')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Leaders' }))
  await screen.findByText('Global leaderboard')
  expect(screen.getAllByText('#1')).toHaveLength(3)
  expect(screen.getByText('peer')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Profile' }))
  expect(screen.getByText('NTHU department not set')).toBeTruthy()
})

test('empty dashboard and history have useful actions', async () => {
  vi.mocked(api.dashboard).mockResolvedValue({ ...dashboard, lifetime_xp: 0, weekly_xp: 0,
    total_pushups: 0, max_set_personal_best: null, recent_workouts: [] })
  vi.mocked(api.history).mockResolvedValue([])
  render(<App />)
  await screen.findByText('No sessions yet')
  fireEvent.click(screen.getByRole('button', { name: 'History' }))
  await screen.findByText('No workouts recorded')
  fireEvent.click(screen.getByRole('button', { name: 'Start a workout' }))
  expect(screen.getByText(/Pick your/)).toBeTruthy()
})

test('dashboard error can be retried', async () => {
  vi.mocked(api.dashboard).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(dashboard)
  render(<App />)
  await screen.findByText(/Could not load your dashboard: offline/)
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByText('Your progress')
})

test('completed result is a dedicated screen with paths back into the app', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: /Start workout/ }))
  fireEvent.click(screen.getByRole('button', { name: /Max/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Mock finish' }))
  await screen.findByText('✦ New Max Set personal best')
  expect(screen.getByText('1:05')).toBeTruthy()
  expect(screen.getByText('30')).toBeTruthy()
  expect(screen.getByRole('button', { name: /View history/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Back to dashboard/ }))
  await screen.findByText('Your progress')
})

test('interrupted result shows zero XP, and refresh loads a saved result', async () => {
  window.history.replaceState({}, '', '/#/result/7')
  render(<App />)
  await screen.findByText('✦ New Max Set personal best')
  cleanup()
  window.history.replaceState({}, '', '/')
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: /Start workout/ }))
  fireEvent.click(screen.getByRole('button', { name: /Max/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Mock interruption' }))
  await screen.findByText(/This attempt earned no XP or personal best/)
  expect(screen.queryByText('✦ New Max Set personal best')).toBeNull()
  expect(screen.getByText('0')).toBeTruthy()
})

test('navigation warns before leaving an active Max Set', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: /Start workout/ }))
  fireEvent.click(screen.getByRole('button', { name: /Max/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Mock start' }))
  fireEvent.click(screen.getByRole('button', { name: 'RepsCV dashboard' }))
  expect(confirm).toHaveBeenCalled()
  expect(screen.getByText('Camera mode: max_set')).toBeTruthy()
  confirm.mockRestore()
})

test('refresh resumes an active Normal Workout from the server', async () => {
  vi.mocked(api.me).mockResolvedValue({ ...user, active_workout: {
    id: 9, mode: 'normal', rep_count: 4, status: 'active', started_at: '2026-11-11T00:00:00Z',
  } })
  render(<App />)
  await screen.findByText('Normal Workout in progress')
  fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
  await waitFor(() => expect(screen.getByText('Resume workout: 9')).toBeTruthy())
})
