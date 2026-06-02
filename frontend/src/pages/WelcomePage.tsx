import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { extractViewerItemsFromPublicZip, processPublicMri } from '../api/publicApi'
import { useAuth } from '../auth/useAuth'
import type { BrainViewerItem } from '../components/brainViewerUtils'

const Brain3DViewer = lazy(() => import('../components/Brain3DViewer').then((module) => ({ default: module.Brain3DViewer })))

function downloadBlob(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

export function WelcomePage() {
  const { login, register, authError, clearAuthError } = useAuth()
  const [authMode, setAuthMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmittingAuth, setIsSubmittingAuth] = useState(false)
  const [authLocalError, setAuthLocalError] = useState<string | null>(null)

  const [publicFile, setPublicFile] = useState<File | null>(null)
  const [isPublicProcessing, setIsPublicProcessing] = useState(false)
  const [publicError, setPublicError] = useState<string | null>(null)
  const [publicStatus, setPublicStatus] = useState<string | null>(null)
  const [publicViewerItems, setPublicViewerItems] = useState<BrainViewerItem[]>([])
  const [publicViewerTitle, setPublicViewerTitle] = useState<string>('3D preview')
  const publicObjectUrlsRef = useRef<string[]>([])

  function clearPublicViewerItems() {
    publicObjectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    publicObjectUrlsRef.current = []
    setPublicViewerItems([])
  }

  useEffect(() => {
    return () => {
      publicObjectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    }
  }, [])

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmittingAuth(true)
    setAuthLocalError(null)
    clearAuthError()

    try {
      if (authMode === 'signup') {
        await register(email, password)
      } else {
        await login(email, password)
      }
    } catch (error) {
      setAuthLocalError(apiMessage(error))
    } finally {
      setIsSubmittingAuth(false)
    }
  }

  async function handlePublicSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!publicFile) {
      setPublicError('Choose a .nii or .nii.gz MRI file first.')
      return
    }

    setIsPublicProcessing(true)
    setPublicError(null)
    setPublicStatus('Preparing your MRI scan. This may take a while for larger files.')
    clearPublicViewerItems()

    try {
      const blob = await processPublicMri(publicFile)
      const base = publicFile.name.replace(/\.nii(\.gz)?$/i, '') || 'brain_mri'
      downloadBlob(blob, `${base}_brain_mri_results.zip`)

      const viewerItems = await extractViewerItemsFromPublicZip(blob)
      publicObjectUrlsRef.current = viewerItems.map((item) => item.objectUrl)
      setPublicViewerItems(viewerItems)
      setPublicViewerTitle(`${base} preview`)
      setPublicStatus('Done. The result download has started and the 3D preview is ready below.')
    } catch (error) {
      setPublicError(apiMessage(error))
      setPublicStatus(null)
    } finally {
      setIsPublicProcessing(false)
    }
  }

  return (
    <main className="welcome-page">
      <section className="hero-section">
        <div className="hero-copy">
          <p className="eyebrow">Brain MRI Processing</p>
          <h1>Turn MRI scans into clear 3D brain tissue results.</h1>
          <p className="hero-text">
            Upload a NIfTI MRI scan, generate tissue models, and review measurements in a visual workspace designed
            for users rather than developers.
          </p>
          <div className="hero-actions">
            <a href="#public-upload" className="button-link">Try without an account</a>
            <a href="#account" className="button-link secondary-link">Sign in</a>
          </div>
        </div>

        <div className="hero-card result-card">
          <span className="badge">What you get</span>
          <ul className="feature-list clean-feature-list">
            <li>Prepared brain scan</li>
            <li>3D grey matter, white matter and CSF models</li>
            <li>Volume and surface measurements</li>
            <li>Downloadable result files</li>
            <li>Saved subjects and time comparison after sign-in</li>
          </ul>
        </div>
      </section>

      <section className="welcome-grid page">
        <article className="card public-upload-card" id="public-upload">
          <p className="eyebrow">Quick processing</p>
          <h2>Process one MRI scan</h2>
          <p className="muted">
            Use this for a one-time result download. Create an account when you want to keep subjects, cases,
            dates and comparisons organized.
          </p>

          <form className="form-grid" onSubmit={handlePublicSubmit}>
            <label>
              MRI file
              <input
                type="file"
                accept=".nii,.gz,.nii.gz"
                onChange={(event) => setPublicFile(event.target.files?.[0] ?? null)}
                required
              />
            </label>
            {publicStatus && <p className="info-text">{publicStatus}</p>}
            {publicError && <p className="error-text">{publicError}</p>}
            <button type="submit" disabled={isPublicProcessing}>
              {isPublicProcessing ? 'Processing scan...' : 'Process scan and download results'}
            </button>
          </form>
        </article>

        <article className="card" id="account">
          <p className="eyebrow">Saved workspace</p>
          <h2>{authMode === 'login' ? 'Sign in' : 'Create account'}</h2>
          <p className="muted">
            Sign in to save subjects, keep acquisition dates together, and return to results later.
          </p>

          <div className="segmented-control" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              className={authMode === 'login' ? 'active' : ''}
              onClick={() => setAuthMode('login')}
            >
              Sign in
            </button>
            <button
              type="button"
              className={authMode === 'signup' ? 'active' : ''}
              onClick={() => setAuthMode('signup')}
            >
              New account
            </button>
          </div>

          <form className="form-grid" onSubmit={handleAuthSubmit}>
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
                autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
                required
              />
            </label>
            {(authLocalError || authError) && <p className="error-text">{authLocalError || authError}</p>}
            <button type="submit" disabled={isSubmittingAuth}>
              {isSubmittingAuth ? 'Please wait...' : authMode === 'login' ? 'Sign in' : 'Create account'}
            </button>
          </form>
        </article>
      </section>

      {publicViewerItems.length > 0 && (
        <section className="page public-viewer-section">
          <Suspense fallback={<section className="card"><p className="muted">Loading 3D preview...</p></section>}>
            <Brain3DViewer
              items={publicViewerItems}
              title={publicViewerTitle}
              subtitle="Preview the generated tissue models before saving the downloaded result files."
              loadingText="Loading preview..."
            />
          </Suspense>
        </section>
      )}
    </main>
  )
}
