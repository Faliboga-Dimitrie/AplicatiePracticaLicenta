import { useState } from 'react'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import { LoginPage } from './pages/LoginPage'
import { SubjectsPage } from './pages/SubjectsPage'
import { SubjectCasesPage } from './pages/SubjectCasesPage'
import { CaseDetailPage } from './pages/CaseDetailPage'
import './App.css'

type ViewState =
  | { name: 'subjects' }
  | { name: 'subjectCases'; subjectId: string }
  | { name: 'caseDetail'; subjectId: string; caseId: number }

function AppContent() {
  const { user, isCheckingSession, isAuthenticated, logout, logoutAll } = useAuth()
  const [view, setView] = useState<ViewState>({ name: 'subjects' })

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

  if (!isAuthenticated) {
    return <LoginPage />
  }

  async function handleLogout() {
    await logout()
    setView({ name: 'subjects' })
  }

  async function handleLogoutAll() {
    await logoutAll()
    setView({ name: 'subjects' })
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <strong>Brain MRI Processing</strong>
          <p className="muted">Logged in as {user?.email}</p>
        </div>
        <nav className="button-row">
          <button type="button" className="secondary" onClick={() => setView({ name: 'subjects' })}>
            Subjects
          </button>
          <button type="button" className="secondary" onClick={handleLogoutAll}>
            Logout all
          </button>
          <button type="button" onClick={handleLogout}>
            Logout
          </button>
        </nav>
      </header>

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
