import type { User } from '../types/api'

type HomePageProps = {
  user: User
  onOpenWorkspace: () => void
  onOpenSettings: () => void
}

const upcomingModules = [
  {
    title: '3D tissue viewer',
    description: 'Interactive GLB inspection for grey matter, white matter and CSF meshes.',
  },
  {
    title: 'Statistics dashboard',
    description: 'Volume and surface-area cards, charts and export-ready summaries for processed cases.',
  },
  {
    title: 'Time comparison',
    description: 'Longitudinal comparison across acquisition dates for subjects with multiple MRI cases.',
  },
]

const pipelineSteps = [
  'Upload or reuse a T1-weighted NIfTI MRI',
  'Run reorientation, skull stripping and FAST segmentation',
  'Generate GLB meshes and tissue metrics',
  'Download artifacts or inspect them in future visual modules',
]

export function HomePage({ user, onOpenWorkspace, onOpenSettings }: HomePageProps) {
  return (
    <main className="page stack dashboard-page">
      <section className="dashboard-hero card">
        <div>
          <p className="eyebrow">Workspace home</p>
          <h1>Welcome back, {user.email}</h1>
          <p className="hero-text">
            This is the persistent side of the application. Use it to manage subjects, upload MRI cases,
            start processing jobs, monitor progress and download generated artifacts.
          </p>
          <div className="button-row hero-actions">
            <button type="button" onClick={onOpenWorkspace}>Open subjects workspace</button>
            <button type="button" className="secondary" onClick={onOpenSettings}>Account settings</button>
          </div>
        </div>

        <aside className="hero-summary-card">
          <p className="eyebrow">Current role</p>
          <h2>Authenticated operator</h2>
          <p className="muted">
            Your authenticated session unlocks persistent subject/case storage, job control and artifact access.
            Anonymous users can only use the temporary public ZIP workflow.
          </p>
        </aside>
      </section>

      <section className="dashboard-grid">
        <article className="card stack">
          <div>
            <p className="eyebrow">Main workflow</p>
            <h2>Persistent MRI workspace</h2>
            <p className="muted">
              The tested smoke-flow is now available from the browser: subject selection, case upload,
              preprocessing, mesh analysis, job polling, cancellation and artifact download.
            </p>
          </div>

          <ol className="timeline-list">
            {pipelineSteps.map((step, index) => (
              <li key={step}>
                <span>{index + 1}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>

          <button type="button" onClick={onOpenWorkspace}>Start from subjects</button>
        </article>

        <article className="card stack">
          <div>
            <p className="eyebrow">Coming next</p>
            <h2>Analysis modules</h2>
            <p className="muted">
              These actions are intentionally disabled for now. They reserve the final app flow without pretending
              those screens are already implemented.
            </p>
          </div>

          <div className="feature-card-list">
            {upcomingModules.map((module) => (
              <div className="feature-card disabled-feature" key={module.title}>
                <div>
                  <strong>{module.title}</strong>
                  <p className="muted">{module.description}</p>
                </div>
                <button type="button" disabled>Coming soon</button>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-grid three-cards">
        <article className="metric-card card">
          <span className="metric-value">01</span>
          <h3>Validated backend</h3>
          <p className="muted">The browser flow now covers the same ground as the original API smoke test.</p>
        </article>
        <article className="metric-card card">
          <span className="metric-value">02</span>
          <h3>Persistent mode</h3>
          <p className="muted">Logged-in work is connected to users, subjects, cases and protected artifacts.</p>
        </article>
        <article className="metric-card card">
          <span className="metric-value">03</span>
          <h3>Public mode</h3>
          <p className="muted">Guests can still process one MRI through the temporary ZIP-based route.</p>
        </article>
      </section>
    </main>
  )
}
