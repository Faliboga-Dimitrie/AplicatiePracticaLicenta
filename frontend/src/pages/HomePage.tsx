import type { User } from '../types/api'

type HomePageProps = {
  user: User
  onOpenWorkspace: () => void
  onOpenSettings: () => void
}

const reviewCards = [
  {
    title: 'Manage people and scans',
    text: 'Keep each subject together with their MRI acquisitions and notes.',
  },
  {
    title: 'Prepare scans when needed',
    text: 'Start the required processing from a single guided case page.',
  },
  {
    title: 'Review results visually',
    text: 'Open the 3D model, inspect measurements, and compare dates over time.',
  },
]

const workflow = [
  'Create or open a subject',
  'Upload a T1 MRI scan for an acquisition date',
  'Prepare the scan, then create the 3D model and measurements',
  'Review the model, statistics, comparison, or download files',
]

export function HomePage({ user, onOpenWorkspace, onOpenSettings }: HomePageProps) {
  const firstName = user.email.split('@')[0]

  return (
    <main className="page stack dashboard-page">
      <section className="dashboard-hero card user-hero-card">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>Welcome back, {firstName}</h1>
          <p className="hero-text">
            Continue working with saved MRI scans, create new subject records, and open finished results without
            needing to follow the technical processing details.
          </p>
          <div className="button-row hero-actions">
            <button type="button" onClick={onOpenWorkspace}>Open subjects</button>
            <button type="button" className="secondary" onClick={onOpenSettings}>Account settings</button>
          </div>
        </div>

        <aside className="hero-summary-card">
          <p className="eyebrow">Signed in as</p>
          <h2>{user.email}</h2>
          <p className="muted">
            Your scans and results are saved to your account so you can return later and compare acquisitions over time.
          </p>
        </aside>
      </section>

      <section className="dashboard-grid">
        <article className="card stack">
          <div>
            <p className="eyebrow">Recommended flow</p>
            <h2>Start from a subject</h2>
            <p className="muted">
              The app now guides the user by result-oriented steps instead of exposing implementation details.
            </p>
          </div>

          <ol className="timeline-list">
            {workflow.map((step, index) => (
              <li key={step}>
                <span>{index + 1}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>

          <button type="button" onClick={onOpenWorkspace}>Go to subjects</button>
        </article>

        <article className="card stack">
          <div>
            <p className="eyebrow">What you can do</p>
            <h2>Review MRI results</h2>
            <p className="muted">
              Once a scan is processed, the result pages can also be opened directly from the sidebar.
            </p>
          </div>

          <div className="feature-card-list">
            {reviewCards.map((card) => (
              <div className="feature-card" key={card.title}>
                <div>
                  <strong>{card.title}</strong>
                  <p className="muted">{card.text}</p>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-grid three-cards">
        <article className="metric-card card">
          <span className="metric-value">3D</span>
          <h3>Interactive model</h3>
          <p className="muted">Toggle brain tissues, rotate the view, and adjust display settings.</p>
        </article>
        <article className="metric-card card">
          <span className="metric-value">Σ</span>
          <h3>Measurements</h3>
          <p className="muted">Review tissue volumes and surface areas in millimetres or centimetres.</p>
        </article>
        <article className="metric-card card">
          <span className="metric-value">↔</span>
          <h3>Evolution</h3>
          <p className="muted">Compare different acquisition dates for the same subject.</p>
        </article>
      </section>
    </main>
  )
}
