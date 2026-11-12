import { useState } from 'react'
import { api, type User } from '../api'

type Props = { user: User; onUpdate: (user: User) => void; onLogout: () => Promise<void> }

export default function Profile({ user, onUpdate, onLogout }: Props) {
  const [department, setDepartment] = useState(user.department ?? '')
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function save(value: string) {
    if (working) return
    setWorking(true)
    setError('')
    setMessage('')
    try {
      const updated = await api.profile(value, user.csrf_token) as User
      onUpdate({ ...user, department: updated.department })
      setDepartment(updated.department ?? '')
      setMessage(updated.department ? 'Department saved.' : 'Department cleared.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update profile.')
    } finally { setWorking(false) }
  }

  async function logout() {
    if (working) return
    setWorking(true)
    setError('')
    try { await onLogout() }
    catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not log out.')
      setWorking(false)
    }
  }

  return (
    <div className="screen profile-screen">
      <div className="screen-heading"><p className="eyebrow">Your corner</p><h1>Built by<br /><em>showing up.</em></h1><p>A little about the person behind the reps.</p></div>
      <section className="profile-card" aria-label="Profile details">
        <div className="profile-monogram" aria-hidden="true">{user.username.slice(0, 1).toUpperCase()}</div>
        <div><span className="overline">Username</span><h2>{user.username}</h2><p>{user.department || 'NTHU department not set'}</p></div>
      </section>
      <section className="form-card">
        <p className="eyebrow">Profile details</p><h2>NTHU department</h2>
        <p>Optional. This is profile information only and does not affect XP.</p>
        <label htmlFor="department">Department</label>
        <input id="department" value={department} onChange={(event) => setDepartment(event.target.value)} maxLength={100} placeholder="e.g. Computer Science" />
        <div className="form-actions"><button type="button" onClick={() => save(department)} disabled={working}>Save department</button><button type="button" className="button-ghost" onClick={() => save('')} disabled={working || !user.department}>Clear</button></div>
        {message && <p className="success-message" role="status">{message}</p>}
        {error && <p className="error-message" role="alert">{error}</p>}
      </section>
      <button type="button" className="logout-button" onClick={logout} disabled={working}>Log out <span aria-hidden="true">↗</span></button>
    </div>
  )
}
