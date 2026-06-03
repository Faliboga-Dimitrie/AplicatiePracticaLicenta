import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'

type LoginPageProps = {
  onBackHome: () => void
}

export function LoginPage({ onBackHome }: LoginPageProps) {
  const { login, register, clearAuthError } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setLocalError(null)
    clearAuthError()

    try {
      if (mode === 'signup') {
        await register(email, password)
      } else {
        await login(email, password)
      }
    } catch {
      setLocalError(mode === 'login' ? 'Email or password invalid.' : 'This email has already been taken.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="welcome-page auth-page">
      <section className="card login-card auth-card">
        <button type="button" className="link-button" onClick={onBackHome}>
          ← Back to public processing
        </button>

        <div>
          <p className="eyebrow">Brain MRI Processing</p>
          <h1>{mode === 'login' ? 'Welcome back' : 'Create your account'}</h1>
          <p className="muted">
            {mode === 'login'
              ? 'Sign in to access your saved MRI subjects, scans and results.'
              : 'Create an account to save MRI subjects, keep acquisition dates organized and compare results over time.'}
          </p>
        </div>

        <div className="segmented-control" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            className={mode === 'login' ? 'active' : ''}
            onClick={() => {
              setMode('login')
              setLocalError(null)
              clearAuthError()
            }}
          >
            Login
          </button>
          <button
            type="button"
            className={mode === 'signup' ? 'active' : ''}
            onClick={() => {
              setMode('signup')
              setLocalError(null)
              clearAuthError()
            }}
          >
            Sign up
          </button>
        </div>

        <form className="form-grid" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
            />
          </label>

          {localError && <p className="error-text">{localError}</p>}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Please wait...' : mode === 'login' ? 'Login' : 'Sign up'}
          </button>
        </form>
      </section>
    </main>
  )
}
