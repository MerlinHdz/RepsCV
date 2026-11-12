import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'
import { api, type WorkoutResult } from './api'

vi.mock('./api', () => ({ api: {
  me: vi.fn(), register: vi.fn(), login: vi.fn(), logout: vi.fn(),
  history: vi.fn(), profile: vi.fn(), status: vi.fn(),
} }))

vi.mock('./PoseDetector', () => ({ default: ({ mode, resume, onResult }: {
  mode: string; resume?: { id: number }; onResult: (result: WorkoutResult) => void
}) => <div>
  <p>Camera mode: {mode}</p>
  {resume && <p>Resume workout: {resume.id}</p>}
  <button onClick={() => onResult({ type: 'workout_result', session_id: 1,
    mode: mode as WorkoutResult['mode'], status: 'completed', rep_count: 3,
    duration_ms: 65000, xp_earned: 30, new_personal_best: true,
    completed_at: '2026-11-11T00:00:00Z' })}>Show completed result</button>
  <button onClick={() => onResult({ type: 'workout_result', session_id: 1,
    mode: mode as WorkoutResult['mode'], status: 'interrupted', rep_count: 3,
    duration_ms: 65000, xp_earned: 0, new_personal_best: false,
    completed_at: null })}>Show interrupted result</button>
</div> }))

const user = { id: 1, username: 'student', department: null, csrf_token: 'csrf', active_workout: null }

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  vi.mocked(api.history).mockResolvedValue([])
})

afterEach(cleanup)

test('registers, chooses Push-ups, and enters Normal Workout camera setup', async () => {
  vi.mocked(api.me).mockRejectedValueOnce(new Error('Login required')).mockResolvedValue(user)
  vi.mocked(api.register).mockResolvedValue(user)
  render(<App />)
  fireEvent.click(await screen.findByText(/Register$/))
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'student' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Register' }))
  await screen.findByText(/Ready for push-ups/)
  fireEvent.click(screen.getByRole('button', { name: /Normal Workout/ }))
  expect(screen.getByText('Camera mode: normal')).toBeTruthy()
})

test('completed Max Set result shows reps, duration, XP, and new PB', async () => {
  vi.mocked(api.me).mockResolvedValue(user)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: /Max Set/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Show completed result' }))
  await waitFor(() => expect(screen.getByText('Workout completed')).toBeTruthy())
  expect(screen.getByText('3')).toBeTruthy()
  expect(screen.getByText('1:05')).toBeTruthy()
  expect(screen.getByText('30')).toBeTruthy()
  expect(screen.getByText('New Max Set personal best!')).toBeTruthy()
})

test('interrupted Max Set result shows zero XP and no PB', async () => {
  vi.mocked(api.me).mockResolvedValue(user)
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: /Max Set/ }))
  fireEvent.click(screen.getByRole('button', { name: 'Show interrupted result' }))
  await screen.findByText(/Interrupted — no XP or personal best/)
  expect(screen.getByText('0')).toBeTruthy()
  expect(screen.queryByText('New Max Set personal best!')).toBeNull()
})

test('refresh resumes an active Normal Workout from the server', async () => {
  vi.mocked(api.me).mockResolvedValue({ ...user, active_workout: {
    id: 9, mode: 'normal', rep_count: 4, status: 'active', started_at: '2026-11-11T00:00:00Z',
  } })
  render(<App />)
  await screen.findByText('Resume workout: 9')
  expect(screen.getByText('Camera mode: normal')).toBeTruthy()
})

test('refresh can recover an interrupted Max Set result', async () => {
  sessionStorage.setItem('repscv_workout_id', '7')
  vi.mocked(api.me).mockResolvedValue(user)
  vi.mocked(api.status).mockResolvedValue({ type: 'workout_result', session_id: 7,
    mode: 'max_set', status: 'interrupted', rep_count: 2, duration_ms: 2200,
    xp_earned: 0, new_personal_best: false, completed_at: null })
  render(<App />)
  await screen.findByText(/Interrupted — no XP or personal best/)
  expect(sessionStorage.getItem('repscv_workout_id')).toBeNull()
})
