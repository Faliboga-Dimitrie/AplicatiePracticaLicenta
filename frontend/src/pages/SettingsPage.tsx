import { useState } from 'react'
import type { User } from '../types/api'

type SettingsPageProps = {
  user: User
  onBackHome: () => void
  onLogout: () => Promise<void>
  onLogoutAll: () => Promise<void>
  onDeleteAccount: () => Promise<void>
}

export function SettingsPage({ user, onBackHome, onLogout, onLogoutAll, onDeleteAccount }: SettingsPageProps) {
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false)
  const [isDeletingAccount, setIsDeletingAccount] = useState(false)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')

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

  async function handleDeleteAccount() {
    if (deleteConfirmation !== user.email) return

    const confirmed = window.confirm(
      'Delete this account permanently? Saved subjects that are only linked to this account may also be removed.',
    )
    if (!confirmed) return

    setIsDeletingAccount(true)
    try {
      await onDeleteAccount()
    } finally {
      setIsDeletingAccount(false)
    }
  }

  return (
    <main className="page stack settings-page">
      <button type="button" className="link-button" onClick={onBackHome}>← Back home</button>

      <section className="card settings-header">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Account settings</h1>
          <p className="muted">Manage your sign-in session and account-level actions.</p>
        </div>
      </section>

      <section className="settings-grid">
        <article className="card stack">
          <div>
            <p className="eyebrow">Account</p>
            <h2>Profile</h2>
          </div>
          <dl className="details-list">
            <div><dt>Email</dt><dd>{user.email}</dd></div>
          </dl>
        </article>

        <article className="card stack">
          <div>
            <p className="eyebrow">Sign out</p>
            <h2>Session options</h2>
            <p className="muted">
              Sign out of this browser, or sign out everywhere if you used the app on another device.
            </p>
          </div>
          <div className="button-row">
            <button type="button" className="secondary" onClick={handleLogout} disabled={isLoggingOut}>
              {isLoggingOut ? 'Signing out...' : 'Sign out here'}
            </button>
            <button type="button" onClick={handleLogoutAll} disabled={isLoggingOutAll}>
              {isLoggingOutAll ? 'Signing out everywhere...' : 'Sign out everywhere'}
            </button>
          </div>
        </article>

        <article className="card stack danger-zone">
          <div>
            <p className="eyebrow">Danger zone</p>
            <h2>Delete account</h2>
            <p className="muted">
              This permanently removes your account. Type your email to confirm before continuing.
            </p>
          </div>
          <label>
            Type your email to confirm
            <input
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              placeholder={user.email}
            />
          </label>
          <button
            type="button"
            className="danger-button"
            onClick={handleDeleteAccount}
            disabled={deleteConfirmation !== user.email || isDeletingAccount}
          >
            {isDeletingAccount ? 'Deleting account...' : 'Delete account permanently'}
          </button>
        </article>
      </section>
    </main>
  )
}
