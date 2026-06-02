import { useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { useAuth } from '../auth/useAuth'

export function LoginPage() {
  const { login, authError, clearAuthError } = useAuth()
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
      await login(email, password)
    } catch (error) {
      setLocalError(apiMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="page centered-page">
      <section className="card login-card">
        <div>
          <p className="eyebrow">Brain MRI Processing</p>
          <h1>Sign in</h1>
          <p className="muted">Access your saved MRI subjects, scans and results.</p>
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
              autoComplete="current-password"
              required
            />
          </label>

          {(localError || authError) && <p className="error-text">{localError || authError}</p>}

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  )
}
