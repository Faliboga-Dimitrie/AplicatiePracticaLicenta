import { useState } from 'react'
import type { User } from '../types/api'

type SettingsPageProps = {
  user: User
  onBackHome: () => void
  onLogout: () => Promise<void>
  onLogoutAll: () => Promise<void>
}

export function SettingsPage({ user, onBackHome, onLogout, onLogoutAll }: SettingsPageProps) {
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false)

  async function handleLogout() {
    setIsLoggingOut(true)
    try {
      await onLogout()
    } finally {
      setIsLoggingOut(false)
    }
  }

  async function handleLogoutAll() {
    setIsLoggingOutAll(true)
    try {
      await onLogoutAll()
    } finally {
      setIsLoggingOutAll(false)
    }
  }

  return (
    <main className="page stack settings-page">
      <button type="button" className="link-button" onClick={onBackHome}>← Back home</button>

      <section className="card settings-header">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Account and session controls</h1>
          <p className="muted">
            Manage the current authenticated session. More account-management actions can live here as the
            backend grows.
          </p>
        </div>
      </section>

      <section className="settings-grid">
        <article className="card stack">
          <div>
            <p className="eyebrow">Account</p>
            <h2>Profile</h2>
          </div>
          <dl className="details-list">
            <div><dt>User ID</dt><dd>{user.id}</dd></div>
            <div><dt>Email</dt><dd>{user.email}</dd></div>
            <div><dt>Status</dt><dd>Active</dd></div>
          </dl>
        </article>

        <article className="card stack">
          <div>
            <p className="eyebrow">Sessions</p>
            <h2>Logout options</h2>
            <p className="muted">
              Logout ends this browser session. Logout all revokes every refresh session for this account,
              including other browsers.
            </p>
          </div>
          <div className="button-row">
            <button type="button" className="secondary" onClick={handleLogout} disabled={isLoggingOut}>
              {isLoggingOut ? 'Logging out...' : 'Logout this browser'}
            </button>
            <button type="button" onClick={handleLogoutAll} disabled={isLoggingOutAll}>
              {isLoggingOutAll ? 'Logging out all...' : 'Logout all sessions'}
            </button>
          </div>
        </article>

        <article className="card stack danger-zone">
          <div>
            <p className="eyebrow">Danger zone</p>
            <h2>Account deletion</h2>
            <p className="muted">
              Placeholder for a future endpoint that should remove the user, refresh sessions, subject access
              rows and decide what happens with owned subjects/cases.
            </p>
          </div>
          <button type="button" disabled>Delete account — coming soon</button>
        </article>
      </section>
    </main>
  )
}
