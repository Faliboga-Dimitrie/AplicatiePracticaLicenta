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
    if (deleteConfirmation !== user.email) {
      return
    }

    const confirmed = window.confirm(
      'Delete this account permanently? Subjects without a remaining editor/admin/owner will also be deleted with their cases and local workspaces.',
    )
    if (!confirmed) {
      return
    }

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
              This permanently deletes your user account and refresh sessions. Subjects are deleted only if,
              after removing your account, no remaining user has editor/admin/owner access. Subjects with
              another maintainer are kept.
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
