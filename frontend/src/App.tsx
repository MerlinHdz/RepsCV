import { useCallback, useEffect, useRef, useState } from 'react'
import PoseDetector from './PoseDetector'
import { api, type ActiveWorkout, type Mode, type User, type WorkoutResult } from './api'
import { parseRoute, routeHash, type Route, type RouteName } from './route'
import Auth from './screens/Auth'
import Dashboard from './screens/Dashboard'
import History from './screens/History'
import Leaderboard from './screens/Leaderboard'
import Profile from './screens/Profile'
import ResultRoute from './screens/ResultRoute'
import WorkoutSelect from './screens/WorkoutSelect'
import './App.css'

const NAV: { name: RouteName; label: string }[] = [
  { name: 'dashboard', label: 'Home' },
  { name: 'workout', label: 'Workout' },
  { name: 'history', label: 'History' },
  { name: 'leaderboard', label: 'Leaders' },
  { name: 'profile', label: 'Profile' },
]

function NavIcon({ name }: { name: RouteName }) {
  const paths: Record<string, string> = {
    dashboard: 'M3 10.5 12 3l9 7.5M5.5 9.5V21h13V9.5M9 21v-7h6v7',
    workout: 'M2 9v6m3-9v12m3-10v8m8-8v8m3-10v12m3-9v6M8 12h8',
    history: 'M4 4v5h5M4.5 9A8.5 8.5 0 1 1 3.5 14M12 7v5l3 2',
    leaderboard: 'M4 20v-7h5v7M10 20V4h5v16M16 20v-10h5v10M2 20h20',
    profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7',
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}

function App() {
  const [booting, setBooting] = useState(true)
  const [user, setUser] = useState<User | null>(null)
  const [activeWorkout, setActiveWorkout] = useState<ActiveWorkout | null>(null)
  const [selectedMode, setSelectedMode] = useState<Mode | null>(null)
  const [resultCache, setResultCache] = useState<WorkoutResult | null>(null)
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash))
  const routeRef = useRef(route)
  const activeRef = useRef<ActiveWorkout | null>(null)

  const updateActive = useCallback((session: ActiveWorkout | null) => {
    activeRef.current = session
    setActiveWorkout(session)
  }, [])

  const go = useCallback((next: Route, force = false): boolean => {
    const previous = routeRef.current
    const active = activeRef.current
    if (!force && previous.name === 'workout' && next.name !== 'workout' && active) {
      const warning = active.mode === 'max_set'
        ? 'Leaving now will interrupt your Max Set and earn no XP. Leave anyway?'
        : 'Leave the camera? Your Normal Workout will stay active so you can resume it later.'
      if (!window.confirm(warning)) return false
      if (active.mode === 'max_set') updateActive(null)
    }
    routeRef.current = next
    setRoute(next)
    if (next.name !== 'workout') setSelectedMode(null)
    window.location.hash = routeHash(next)
    return true
  }, [updateActive])

  useEffect(() => {
    const handleHash = () => {
      const next = parseRoute(window.location.hash)
      const previous = routeRef.current
      if (routeHash(next) === routeHash(previous)) return
      const active = activeRef.current
      if (previous.name === 'workout' && next.name !== 'workout' && active) {
        const warning = active.mode === 'max_set'
          ? 'Leaving now will interrupt your Max Set and earn no XP. Leave anyway?'
          : 'Leave the camera? Your Normal Workout will stay active so you can resume it later.'
        if (!window.confirm(warning)) {
          window.location.hash = routeHash(previous)
          return
        }
        if (active.mode === 'max_set') updateActive(null)
      }
      routeRef.current = next
      setRoute(next)
      if (next.name !== 'workout') setSelectedMode(null)
    }
    window.addEventListener('hashchange', handleHash)
    return () => window.removeEventListener('hashchange', handleHash)
  }, [updateActive])

  useEffect(() => {
    if (activeWorkout?.mode !== 'max_set' || route.name !== 'workout') return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [activeWorkout?.mode, route.name])

  useEffect(() => {
    let current = true
    api.me().then(async (account) => {
      if (!current) return
      setUser(account)
      updateActive(account.active_workout ?? null)
      if (account.active_workout?.mode === 'max_set') {
        go({ name: 'workout' }, true)
      } else if (!account.active_workout) {
        const pendingId = Number(sessionStorage.getItem('repscv_workout_id'))
        if (Number.isInteger(pendingId) && pendingId > 0) {
          try {
            const status = await api.status(pendingId)
            if (current && status.status !== 'active') {
              setResultCache(status as WorkoutResult)
              go({ name: 'result', sessionId: pendingId }, true)
            }
          } catch { /* A stale ID belongs to no accessible result. */ }
          sessionStorage.removeItem('repscv_workout_id')
        }
      }
      if (current) setBooting(false)
    }).catch(() => { if (current) { setUser(null); setBooting(false) } })
    return () => { current = false }
  }, [go, updateActive])

  const onAuthenticated = useCallback((account: User) => {
    setUser(account)
    updateActive(account.active_workout ?? null)
    if (account.active_workout?.mode === 'max_set') go({ name: 'workout' }, true)
    else go({ name: 'dashboard' }, true)
  }, [go, updateActive])

  const onResult = useCallback((saved: WorkoutResult) => {
    sessionStorage.removeItem('repscv_workout_id')
    setResultCache(saved)
    updateActive(null)
    setSelectedMode(null)
    go({ name: 'result', sessionId: saved.session_id }, true)
  }, [go, updateActive])

  const logout = useCallback(async () => {
    if (!user) return
    await api.logout(user.csrf_token)
    sessionStorage.removeItem('repscv_workout_id')
    updateActive(null)
    setUser(null)
    setResultCache(null)
    go({ name: 'dashboard' }, true)
  }, [user, go, updateActive])

  const openWorkout = (sessionId: number) => go({ name: 'result', sessionId })
  const startWorkout = () => { setSelectedMode(null); go({ name: 'workout' }) }

  if (booting) return <main className="boot-screen" role="status"><span className="brand-mark">R<span>↗</span></span><p>Loading RepsCV…</p></main>
  if (!user) return <Auth onAuthenticated={onAuthenticated} />

  const focusWorkout = route.name === 'workout' && activeWorkout !== null
  return <div className="app-shell">
    <header className="app-header">
      <button type="button" className="brand-button" onClick={() => go({ name: 'dashboard' })} aria-label="RepsCV dashboard"><span className="brand-mark">R<span>↗</span></span><span>RepsCV</span></button>
      <span className="header-caption">BUILT BY THE REP</span>
      <button type="button" className="header-profile" onClick={() => go({ name: 'profile' })} aria-label="Open profile">{user.username.slice(0, 1).toUpperCase()}</button>
    </header>

    <div className="app-main">
      {route.name === 'dashboard' && <Dashboard user={user} activeWorkout={activeWorkout} onStart={startWorkout}
        onResume={() => go({ name: 'workout' })} onHistory={() => go({ name: 'history' })} onOpenWorkout={openWorkout} />}
      {route.name === 'history' && <History onStart={startWorkout} onOpenWorkout={openWorkout} />}
      {route.name === 'leaderboard' && <Leaderboard />}
      {route.name === 'profile' && <Profile user={user} onUpdate={setUser} onLogout={logout} />}
      {route.name === 'workout' && (selectedMode || activeWorkout
        ? <PoseDetector key={selectedMode ?? activeWorkout?.id} mode={selectedMode ?? activeWorkout!.mode}
            csrfToken={user.csrf_token} resume={selectedMode ? undefined : activeWorkout ?? undefined}
            onSessionStarted={updateActive} onResult={onResult} onBack={() => setSelectedMode(null)} />
        : <WorkoutSelect onSelect={setSelectedMode} onBack={() => go({ name: 'dashboard' })} />)}
      {route.name === 'result' && route.sessionId && <ResultRoute key={route.sessionId}
        sessionId={route.sessionId} initial={resultCache} onDashboard={() => go({ name: 'dashboard' })}
        onHistory={() => go({ name: 'history' })} onNewWorkout={startWorkout} />}
    </div>

    {!focusWorkout && route.name !== 'result' && <nav className="bottom-nav" aria-label="Main navigation">
      {NAV.map(({ name, label }) => <button key={name} type="button" onClick={() => go({ name })}
        aria-current={route.name === name ? 'page' : undefined}>
        <NavIcon name={name} /><span>{label}</span>
      </button>)}
    </nav>}
  </div>
}

export default App
