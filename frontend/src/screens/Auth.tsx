import { useState, type FormEvent } from 'react'
import { api, type User } from '../api'

type Props = { onAuthenticated: (user: User) => void }

export default function Auth({ onAuthenticated }: Props) {
  const [registering, setRegistering] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [department, setDepartment] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (working) return
    setWorking(true)
    setError('')
    try {
      if (registering) await api.register(username, password, department)
      else await api.login(username, password)
      const user = await api.me()
      onAuthenticated(user)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign in.')
    } finally { setWorking(false) }
  }

  return <main className="auth-layout">
    <div className="auth-brand"><span className="brand-mark">R<span>↗</span></span><span>RepsCV</span></div>
    <div className="auth-copy"><p className="eyebrow">Built one rep at a time</p><h1>Show up.<br /><em>Get stronger.</em></h1><p>Track the work. Own your progress.</p></div>
    <form className="auth-card" onSubmit={submit}>
      <p className="eyebrow">{registering ? 'Join the movement' : 'Back for more'}</p>
      <h2>{registering ? 'Create your account' : 'Welcome back'}</h2>
      <label htmlFor="username">Username</label><input id="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={20} autoComplete="username" placeholder="Your username" />
      <label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete={registering ? 'new-password' : 'current-password'} placeholder="At least 8 characters" />
      {registering && <><label htmlFor="department">NTHU department <small>optional</small></label><input id="department" value={department} onChange={(event) => setDepartment(event.target.value)} maxLength={100} placeholder="e.g. Computer Science" /></>}
      {error && <p className="error-message" role="alert">{error}</p>}
      <button type="submit" disabled={working}>{working ? 'Please wait…' : registering ? 'Create account' : 'Log in'} <span aria-hidden="true">↗</span></button>
      <button className="auth-switch" type="button" onClick={() => { setRegistering(!registering); setError('') }}>
        {registering ? 'Already have an account? Log in' : 'New to RepsCV? Create an account'}
      </button>
    </form>
  </main>
}
