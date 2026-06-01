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
  const [publicViewerTitle, setPublicViewerTitle] = useState<string>('Public MRI preview')
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
      setPublicError('Choose a .nii or .nii.gz file first.')
      return
    }

    setIsPublicProcessing(true)
    setPublicError(null)
    setPublicStatus('Uploading and processing MRI. This can take several minutes...')
    clearPublicViewerItems()

    try {
      const blob = await processPublicMri(publicFile)
      const base = publicFile.name.replace(/\.nii(\.gz)?$/i, '') || 'brain_mri'
      downloadBlob(blob, `${base}_brain_mri_outputs.zip`)

      const viewerItems = await extractViewerItemsFromPublicZip(blob)
      publicObjectUrlsRef.current = viewerItems.map((item) => item.objectUrl)
      setPublicViewerItems(viewerItems)
      setPublicViewerTitle(`${base} preview`)
      setPublicStatus('Processing completed. Your ZIP download should start automatically, and the GLB preview is ready below.')
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
          <h1>From T1 MRI to segmented 3D brain tissue models.</h1>
          <p className="hero-text">
            Upload a NIfTI MRI and generate tissue meshes plus volume/surface metrics.
            Use the public quick processing route for one-off downloads, or sign in to manage subjects,
            cases, processing jobs and artifacts over time.
          </p>
          <div className="hero-actions">
            <a href="#public-upload" className="button-link">Try public processing</a>
            <a href="#account" className="button-link secondary-link">Log in or sign up</a>
          </div>
        </div>

        <div className="hero-card">
          <span className="badge">Current pipeline</span>
          <ul className="feature-list">
            <li>Reorientation to standard space</li>
            <li>Skull stripping with HD-BET</li>
            <li>FAST tissue segmentation</li>
            <li>GLB mesh export</li>
            <li>Volume and surface metrics</li>
          </ul>
        </div>
      </section>

      <section className="welcome-grid page">
        <article className="card public-upload-card" id="public-upload">
          <p className="eyebrow">No account needed</p>
          <h2>Quick MRI processing</h2>
          <p className="muted">
            This route does not create a subject or case. The backend uses temporary files,
            returns a ZIP, then discards the temporary workspace. The browser can also preview
            the GLB files from that ZIP without storing them permanently.
          </p>

          <form className="form-grid" onSubmit={handlePublicSubmit}>
            <label>
              MRI file
              <input
                type="file"
                accept=".nii,.nii.gz,application/gzip,application/octet-stream"
                onChange={(event) => setPublicFile(event.target.files?.[0] ?? null)}
                disabled={isPublicProcessing}
              />
            </label>
            {publicStatus && <p className="info-text">{publicStatus}</p>}
            {publicError && <p className="error-text">{publicError}</p>}
            <button type="submit" disabled={isPublicProcessing || !publicFile}>
              {isPublicProcessing ? 'Processing...' : 'Process, download ZIP and preview GLBs'}
            </button>
          </form>
        </article>

        <article className="card" id="account">
          <p className="eyebrow">Persistent workspace</p>
          <h2>{authMode === 'signup' ? 'Create account' : 'Log in'}</h2>
          <p className="muted">
            Sign in to keep subjects, acquisition dates, job history, case readiness and artifacts organized.
          </p>

          <div className="segmented-control" aria-label="Authentication mode">
            <button
              type="button"
              className={authMode === 'login' ? 'active' : 'secondary'}
              onClick={() => setAuthMode('login')}
            >
              Log in
            </button>
            <button
              type="button"
              className={authMode === 'signup' ? 'active' : 'secondary'}
              onClick={() => setAuthMode('signup')}
            >
              Sign up
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
                autoComplete={authMode === 'signup' ? 'new-password' : 'current-password'}
                required
              />
            </label>

            {(authLocalError || authError) && <p className="error-text">{authLocalError || authError}</p>}

            <button type="submit" disabled={isSubmittingAuth}>
              {isSubmittingAuth
                ? authMode === 'signup' ? 'Creating account...' : 'Signing in...'
                : authMode === 'signup' ? 'Create account' : 'Sign in'}
            </button>
          </form>
        </article>
      </section>

      {publicViewerItems.length > 0 && (
        <section className="page public-viewer-section">
          <section className="page-header-card viewer-header-card">
            <div>
              <p className="eyebrow">Public 3D preview</p>
              <h1>{publicViewerTitle}</h1>
              <p className="muted">These object URLs are created in the browser from the downloaded ZIP and are discarded when you leave or process another file.</p>
            </div>
            <button type="button" className="secondary" onClick={clearPublicViewerItems}>Clear preview</button>
          </section>
          <Suspense fallback={<section className="card"><p className="muted">Loading 3D viewer...</p></section>}>
            <Brain3DViewer
              items={publicViewerItems}
              title="Public GLB controls"
              subtitle="Preview meshes directly from the temporary public processing ZIP. No account, subject or case is involved."
            />
          </Suspense>
        </section>
      )}
    </main>
  )
}
