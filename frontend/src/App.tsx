import { useState } from 'react'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import { WelcomePage } from './pages/WelcomePage'
import { HomePage } from './pages/HomePage'
import { SubjectsPage } from './pages/SubjectsPage'
import { SubjectCasesPage } from './pages/SubjectCasesPage'
import { CaseDetailPage } from './pages/CaseDetailPage'
import { SettingsPage } from './pages/SettingsPage'
import './App.css'

type ViewState =
  | { name: 'home' }
  | { name: 'subjects' }
  | { name: 'subjectCases'; subjectId: string }
  | { name: 'caseDetail'; subjectId: string; caseId: number }
  | { name: 'settings' }

function AppContent() {
  const { user, isCheckingSession, isAuthenticated, logout, logoutAll, deleteAccount } = useAuth()
  const [view, setView] = useState<ViewState>({ name: 'home' })

  if (isCheckingSession) {
    return (
      <main className="page centered-page">
        <section className="card">
          <h1>Loading session...</h1>
          <p className="muted">Checking whether your refresh cookie can restore the session.</p>
        </section>
      </main>
    )
  }

  if (!isAuthenticated || !user) {
    return <WelcomePage />
  }

  async function handleLogout() {
    await logout()
    setView({ name: 'home' })
  }

  async function handleLogoutAll() {
    await logoutAll()
    setView({ name: 'home' })
  }

  async function handleDeleteAccount() {
    await deleteAccount()
    setView({ name: 'home' })
  }

  const currentSection = view.name === 'subjects' || view.name === 'subjectCases' || view.name === 'caseDetail'
    ? 'workspace'
    : view.name

  return (
    <div className="app-shell logged-in-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">MRI</span>
          <div>
            <strong>Brain MRI</strong>
            <p>Processing Suite</p>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          <button
            type="button"
            className={currentSection === 'home' ? 'active' : ''}
            onClick={() => setView({ name: 'home' })}
          >
            Home
          </button>
          <button
            type="button"
            className={currentSection === 'workspace' ? 'active' : ''}
            onClick={() => setView({ name: 'subjects' })}
          >
            Subjects & cases
          </button>
          <button type="button" disabled>3D view</button>
          <button type="button" disabled>Statistics</button>
          <button type="button" disabled>Time comparison</button>
          <button
            type="button"
            className={currentSection === 'settings' ? 'active' : ''}
            onClick={() => setView({ name: 'settings' })}
          >
            Settings
          </button>
        </nav>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div>
            <strong>{currentSection === 'workspace' ? 'Persistent workspace' : currentSection === 'settings' ? 'Settings' : 'Home'}</strong>
            <p className="muted">Logged in as {user.email}</p>
          </div>
          <nav className="button-row">
            <button type="button" className="secondary" onClick={() => setView({ name: 'settings' })}>
              Settings
            </button>
            <button type="button" onClick={handleLogout}>
              Logout
            </button>
          </nav>
        </header>

        {view.name === 'home' && (
          <HomePage
            user={user}
            onOpenWorkspace={() => setView({ name: 'subjects' })}
            onOpenSettings={() => setView({ name: 'settings' })}
          />
        )}

        {view.name === 'subjects' && (
          <SubjectsPage onSelectSubject={(subjectId) => setView({ name: 'subjectCases', subjectId })} />
        )}

        {view.name === 'subjectCases' && (
          <SubjectCasesPage
            subjectId={view.subjectId}
            onBack={() => setView({ name: 'subjects' })}
            onSelectCase={(caseId) => setView({ name: 'caseDetail', subjectId: view.subjectId, caseId })}
          />
        )}

        {view.name === 'caseDetail' && (
          <CaseDetailPage
            caseId={view.caseId}
            onBack={() => setView({ name: 'subjectCases', subjectId: view.subjectId })}
          />
        )}

        {view.name === 'settings' && (
          <SettingsPage
            user={user}
            onBackHome={() => setView({ name: 'home' })}
            onLogout={handleLogout}
            onLogoutAll={handleLogoutAll}
            onDeleteAccount={handleDeleteAccount}
          />
        )}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
