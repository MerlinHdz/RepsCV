export type Mode = 'normal' | 'max_set'
export type ActiveWorkout = { id: number; mode: Mode; rep_count: number; status: string; started_at: string }
export type User = { id: number; username: string; department: string | null; csrf_token: string; active_workout?: ActiveWorkout | null }
export type WorkoutResult = {
  type: 'workout_result'; session_id: number; mode: Mode; status: 'completed' | 'interrupted'
  rep_count: number; duration_ms: number | null; xp_earned: number
  new_personal_best: boolean; completed_at: string | null
}
export type StartResponse = ActiveWorkout & { remaining_ms: number | null }
export type DashboardSummary = {
  username: string
  lifetime_xp: number
  weekly_xp: number
  total_pushups: number
  max_set_personal_best: number | null
  recent_workouts: WorkoutResult[]
  week_start: string
  week_end: string
  timezone: 'Asia/Taipei'
}
export type LeaderboardEntry = {
  rank: number; user_id: number; username: string; weekly_xp: number; is_current_user: boolean
}
export type WeeklyLeaderboard = {
  period: 'weekly'; week_start: string; week_end: string; timezone: 'Asia/Taipei'
  current_user_rank: number | null; entries: LeaderboardEntry[]
}

async function request<T>(path: string, method = 'GET', body?: unknown, csrfToken?: string): Promise<T> {
  const response = await fetch(path, {
    method, credentials: 'same-origin',
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`)
  return data as T
}

export const api = {
  me: () => request<User>('/api/auth/me'),
  register: (username: string, password: string, department: string) =>
    request<User>('/api/auth/register', 'POST', { username, password, department: department || null }),
  login: (username: string, password: string) => request<User>('/api/auth/login', 'POST', { username, password }),
  logout: (csrf: string) => request('/api/auth/logout', 'POST', undefined, csrf),
  profile: (department: string, csrf: string) => request('/api/profile', 'PATCH', { department: department || null }, csrf),
  start: (mode: Mode, csrf: string) => request<StartResponse>('/api/workouts/start', 'POST', { exercise: 'pushup', mode }, csrf),
  finish: (id: number, csrf: string) => request<WorkoutResult>(`/api/workouts/${id}/finish`, 'POST', undefined, csrf),
  status: (id: number) => request<ActiveWorkout | WorkoutResult>(`/api/workouts/${id}`),
  history: () => request<WorkoutResult[]>('/api/workouts'),
  dashboard: () => request<DashboardSummary>('/api/dashboard'),
  leaderboard: () => request<WeeklyLeaderboard>('/api/leaderboard?period=weekly'),
}
