import { useState } from 'react'
import { AuthProvider } from './auth/AuthProvider'
import { useAuth } from './auth/useAuth'
import { WelcomePage } from './pages/WelcomePage'
import { HomePage } from './pages/HomePage'
import { SubjectsPage } from './pages/SubjectsPage'
import { SubjectCasesPage } from './pages/SubjectCasesPage'
import { CaseDetailPage } from './pages/CaseDetailPage'
import { SettingsPage } from './pages/SettingsPage'
import { Case3DViewerPage } from './pages/Case3DViewerPage'
import { TimeComparisonPage } from './pages/TimeComparisonPage'
import { StatisticsPage } from './pages/StatisticsPage'
import { JobActivityProvider, useJobActivity } from './jobs/JobActivityProvider'
import './App.css'

type ViewState =
  | { name: 'home' }
  | { name: 'subjects' }
  | { name: 'subjectCases'; subjectId: string }
  | { name: 'caseDetail'; subjectId: string; caseId: number }
  | { name: 'caseViewer'; subjectId: string; caseId: number }
  | { name: 'statistics'; subjectId: string; caseId: number }
  | { name: 'timeComparison'; subjectId: string }
  | { name: 'settings' }

type RecentCase = {
  subjectId: string
  caseId: number
}

function AppContent() {
  const { user, isCheckingSession, isAuthenticated, logout, logoutAll, deleteAccount } = useAuth()
  const { clearAllTrackedJobs } = useJobActivity()
  const [view, setView] = useState<ViewState>({ name: 'home' })
  const [recentCase, setRecentCase] = useState<RecentCase | null>(null)
  const [recentSubjectId, setRecentSubjectId] = useState<string | null>(null)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)

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

  function openCaseDetail(subjectId: string, caseId: number) {
    setRecentSubjectId(subjectId)
    setRecentCase({ subjectId, caseId })
    setView({ name: 'caseDetail', subjectId, caseId })
  }

  function openCaseViewer(subjectId: string, caseId: number) {
    setRecentCase({ subjectId, caseId })
    setRecentSubjectId(subjectId)
    setView({ name: 'caseViewer', subjectId, caseId })
  }


  function openStatistics(subjectId: string, caseId: number) {
    setRecentCase({ subjectId, caseId })
    setRecentSubjectId(subjectId)
    setView({ name: 'statistics', subjectId, caseId })
  }

  function openTimeComparison(subjectId: string) {
    setRecentSubjectId(subjectId)
    setView({ name: 'timeComparison', subjectId })
  }

  async function handleLogout() {
    await logout()
    clearAllTrackedJobs()
    setView({ name: 'home' })
  }

  async function handleLogoutAll() {
    await logoutAll()
    clearAllTrackedJobs()
    setView({ name: 'home' })
  }

  async function handleDeleteAccount() {
    await deleteAccount()
    clearAllTrackedJobs()
    setView({ name: 'home' })
  }

  const currentSection = view.name === 'subjects' || view.name === 'subjectCases' || view.name === 'caseDetail' || view.name === 'caseViewer' || view.name === 'statistics' || view.name === 'timeComparison'
    ? 'workspace'
    : view.name

  return (
    <div className={`app-shell logged-in-shell ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="brand-block">
          <span className="brand-mark">MRI</span>
          {!isSidebarCollapsed && (
            <div>
              <strong>Brain MRI</strong>
              <p>Processing Suite</p>
            </div>
          )}
        </div>

        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setIsSidebarCollapsed((collapsed) => !collapsed)}
          aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isSidebarCollapsed ? '»' : '«'}
        </button>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          <button
            type="button"
            className={currentSection === 'home' ? 'active' : ''}
            onClick={() => setView({ name: 'home' })}
            title="Home"
          >
            <span>Home</span>
          </button>
          <button
            type="button"
            className={currentSection === 'workspace' ? 'active' : ''}
            onClick={() => setView({ name: 'subjects' })}
            title="Subjects & cases"
          >
            <span>Subjects & cases</span>
          </button>
          <button
            type="button"
            className={view.name === 'caseViewer' ? 'active' : ''}
            disabled={!recentCase}
            onClick={() => recentCase && openCaseViewer(recentCase.subjectId, recentCase.caseId)}
            title={recentCase ? 'Open latest 3D viewer' : 'Open a case with meshes first'}
          >
            <span>3D view</span>
          </button>
          <button
            type="button"
            className={view.name === 'statistics' ? 'active' : ''}
            disabled={!recentCase}
            onClick={() => recentCase && openStatistics(recentCase.subjectId, recentCase.caseId)}
            title={recentCase ? 'Open statistics for latest case' : 'Open a metric-ready case first'}
          >
            <span>Statistics</span>
          </button>
          <button
            type="button"
            className={view.name === 'timeComparison' ? 'active' : ''}
            disabled={!recentSubjectId}
            onClick={() => recentSubjectId && openTimeComparison(recentSubjectId)}
            title={recentSubjectId ? 'Compare metric-ready dates for latest subject' : 'Open a subject first'}
          >
            <span>Time comparison</span>
          </button>
          <button
            type="button"
            className={currentSection === 'settings' ? 'active' : ''}
            onClick={() => setView({ name: 'settings' })}
            title="Settings"
          >
            <span>Settings</span>
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
          <SubjectsPage onSelectSubject={(subjectId) => { setRecentSubjectId(subjectId); setView({ name: 'subjectCases', subjectId }) }} />
        )}

        {view.name === 'subjectCases' && (
          <SubjectCasesPage
            subjectId={view.subjectId}
            onBack={() => setView({ name: 'subjects' })}
            onSelectCase={(caseId) => openCaseDetail(view.subjectId, caseId)}
            onOpenTimeComparison={() => openTimeComparison(view.subjectId)}
          />
        )}

        {view.name === 'caseDetail' && (
          <CaseDetailPage
            caseId={view.caseId}
            onBack={() => setView({ name: 'subjectCases', subjectId: view.subjectId })}
            onOpenViewer={() => openCaseViewer(view.subjectId, view.caseId)}
            onOpenStatistics={() => openStatistics(view.subjectId, view.caseId)}
            onOpenTimeComparison={() => openTimeComparison(view.subjectId)}
          />
        )}

        {view.name === 'caseViewer' && (
          <Case3DViewerPage
            caseId={view.caseId}
            onBack={() => openCaseDetail(view.subjectId, view.caseId)}
          />
        )}

        {view.name === 'statistics' && (
          <StatisticsPage
            caseId={view.caseId}
            onBack={() => openCaseDetail(view.subjectId, view.caseId)}
            onOpenViewer={() => openCaseViewer(view.subjectId, view.caseId)}
          />
        )}

        {view.name === 'timeComparison' && (
          <TimeComparisonPage
            subjectId={view.subjectId}
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
      <JobActivityProvider>
        <AppContent />
      </JobActivityProvider>
    </AuthProvider>
  )
}
