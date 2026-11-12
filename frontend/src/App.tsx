import { useCallback, useEffect, useState, type FormEvent } from 'react'
import PoseDetector from './PoseDetector'
import { api, type Mode, type User, type WorkoutResult } from './api'
import { formatDuration, modeLabel, resultLabel } from './sessionUi'
import './App.css'

type Stage = 'loading' | 'auth' | 'choose' | 'camera' | 'result'

function App() {
  const [stage, setStage] = useState<Stage>('loading')
  const [user, setUser] = useState<User | null>(null)
  const [mode, setMode] = useState<Mode>('normal')
  const [result, setResult] = useState<WorkoutResult | null>(null)
  const [recent, setRecent] = useState<WorkoutResult[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [department, setDepartment] = useState('')
  const [registering, setRegistering] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    api.me().then(async (current) => {
      if (!mounted) return
      setUser(current)
      setDepartment(current.department ?? '')
      if (current.active_workout) {
        setMode(current.active_workout.mode)
        setStage('camera')
      } else {
        const pendingId = Number(sessionStorage.getItem('repscv_workout_id'))
        if (Number.isInteger(pendingId) && pendingId > 0) {
          try {
            const pending = await api.status(pendingId)
            if (mounted && pending.status !== 'active') {
              setResult(pending as WorkoutResult)
              setStage('result')
            } else if (mounted) setStage('choose')
          } catch { if (mounted) setStage('choose') }
          sessionStorage.removeItem('repscv_workout_id')
        } else setStage('choose')
      }
      const history = await api.history().catch(() => [])
      if (mounted) setRecent(history)
    }).catch(() => { if (mounted) setStage('auth') })
    return () => { mounted = false }
  }, [])

  async function submitAuth(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const current = registering
        ? await api.register(username, password, department)
        : await api.login(username, password)
      setUser(current)
      setDepartment(current.department ?? '')
      setPassword('')
      const fresh = await api.me()
      setUser(fresh)
      if (fresh.active_workout) {
        setMode(fresh.active_workout.mode)
        setStage('camera')
      } else setStage('choose')
      setRecent(await api.history())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in.')
    } finally { setBusy(false) }
  }

  async function saveDepartment() {
    if (!user || busy) return
    setBusy(true)
    setError('')
    try {
      const updated = await api.profile(department, user.csrf_token) as User
      setUser({ ...user, department: updated.department })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update profile.')
    } finally { setBusy(false) }
  }

  async function logout() {
    if (!user || busy) return
    setBusy(true)
    try {
      await api.logout(user.csrf_token)
      sessionStorage.removeItem('repscv_workout_id')
      setUser(null)
      setRecent([])
      setStage('auth')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not log out.')
    } finally { setBusy(false) }
  }

  const onResult = useCallback((saved: WorkoutResult) => {
    sessionStorage.removeItem('repscv_workout_id')
    setResult(saved)
    setStage('result')
    api.me().then(setUser).catch(() => undefined)
    api.history().then(setRecent).catch(() => undefined)
  }, [])

  if (stage === 'loading') return <main className="shell"><p>Loading RepsCV…</p></main>

  if (stage === 'auth') return (
    <main className="shell auth-screen">
      <p className="eyebrow">RepsCV · Push-up tracker</p>
      <h1>{registering ? 'Create your account' : 'Welcome back'}</h1>
      <form onSubmit={submitAuth}>
        <label>Username<input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={20} autoComplete="username" /></label>
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={registering ? 'new-password' : 'current-password'} /></label>
        {registering && <label>NTHU department (optional)<input value={department} onChange={(event) => setDepartment(event.target.value)} maxLength={100} /></label>}
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? 'Please wait…' : registering ? 'Register' : 'Log in'}</button>
      </form>
      <button className="text-button" type="button" onClick={() => { setRegistering(!registering); setError('') }}>
        {registering ? 'Already have an account? Log in' : 'New to RepsCV? Register'}
      </button>
    </main>
  )

  if (!user) return null
  if (stage === 'camera') return (
    <PoseDetector key={user.active_workout?.id ?? mode} mode={mode} csrfToken={user.csrf_token}
      resume={user.active_workout ?? undefined} onResult={onResult}
      onBack={() => setStage('choose')} />
  )

  if (stage === 'result' && result) return (
    <main className="shell result-screen">
      <p className="eyebrow">RepsCV · Workout result</p>
      <h1>{resultLabel(result)}</h1>
      <div className="result-grid">
        <p><span>Mode</span><strong>{modeLabel(result.mode)}</strong></p>
        <p><span>Valid reps</span><strong>{result.rep_count}</strong></p>
        <p><span>Duration</span><strong>{formatDuration(result.duration_ms)}</strong></p>
        <p><span>XP earned</span><strong>{result.xp_earned}</strong></p>
      </div>
      <p>Status: {result.status === 'completed' ? 'Completed' : 'Interrupted'}</p>
      {result.new_personal_best && <p className="pb">New Max Set personal best!</p>}
      <button type="button" onClick={() => setStage('choose')}>Choose another workout</button>
    </main>
  )

  return (
    <main className="shell choose-screen">
      <div className="top-row"><p className="eyebrow">RepsCV · Push-ups</p><button type="button" className="text-button" onClick={logout} disabled={busy}>Log out</button></div>
      <h1>Ready for push-ups, {user.username}?</h1>
      <p>Choose a mode, prepare your side-view camera, then start the workout.</p>
      <div className="mode-grid">
        <button type="button" onClick={() => { setMode('normal'); setStage('camera') }}><strong>Normal Workout</strong><span>Rest as long as you need. Press Finish when done.</span></button>
        <button type="button" onClick={() => { setMode('max_set'); setStage('camera') }}><strong>Max Set</strong><span>First rep within 20 seconds, then another every 5 seconds.</span></button>
      </div>
      <section className="profile-row"><label>NTHU department (optional)<input value={department} onChange={(event) => setDepartment(event.target.value)} maxLength={100} /></label><button type="button" onClick={saveDepartment} disabled={busy}>Save profile</button></section>
      {error && <p className="error" role="alert">{error}</p>}
      {recent.length > 0 && <section className="recent"><h2>Saved workouts</h2><ul>{recent.slice(0, 5).map((item) => <li key={item.session_id}>{modeLabel(item.mode)} · {item.rep_count} reps · {item.xp_earned} XP · {formatDuration(item.duration_ms)}</li>)}</ul></section>}
    </main>
  )
}

export default App
