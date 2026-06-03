const reviewCards = [
  {
    title: 'Manage people and scans',
    text: 'Keep each subject together with their MRI acquisitions and notes.',
  },
  {
    title: 'Process scans when needed',
    text: 'Start the complete MRI processing flow from a single guided case page.',
  },
  {
    title: 'Review results visually',
    text: 'Open the 3D model, inspect measurements, and compare dates over time.',
  },
]

const workflow = [
  'Create or open a subject from the sidebar',
  'Upload a T1 MRI scan for an acquisition date',
  'Process the MRI to create the 3D model and measurements',
  'Review the model, statistics, comparison, or download files',
]

export function HomePage() {
  return (
    <main className="page stack dashboard-page">
      <section className="dashboard-hero card user-hero-card">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>Welcome back</h1>
          <p className="hero-text">
            Continue working with saved MRI scans, create new subject records, and open finished results without
            needing to follow the technical processing details.
          </p>
        </div>

        <aside className="hero-summary-card">
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
              Use the sidebar to move between subjects, the 3D viewer, measurements, time comparison, and account settings.
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
