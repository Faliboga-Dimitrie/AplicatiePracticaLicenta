import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import {
  downloadPublicProcessingResult,
  extractViewerItemsFromPublicZip,
  getPublicProcessingJob,
  startPublicProcessingJob,
} from '../api/publicApi'
import type { BrainViewerItem } from '../components/brainViewerUtils'
import type { PublicProcessingJob } from '../types/api'

const Brain3DViewer = lazy(() => import('../components/Brain3DViewer').then((module) => ({ default: module.Brain3DViewer })))

type WelcomePageProps = {
  onOpenAuth: () => void
}

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

function getBaseName(fileName: string): string {
  return fileName.replace(/\.nii(\.gz)?$/i, '') || 'brain_mri'
}

function getFriendlyPublicError(error: unknown): string {
  const message = apiMessage(error)
  if (/invalid|nii|upload|file/i.test(message)) {
    return 'Please choose a valid .nii or .nii.gz MRI file and try again.'
  }
  return 'We could not process this MRI. Please check the file and try again.'
}

export function WelcomePage({ onOpenAuth }: WelcomePageProps) {
  const [publicFile, setPublicFile] = useState<File | null>(null)
  const [isPublicProcessing, setIsPublicProcessing] = useState(false)
  const [publicProgress, setPublicProgress] = useState(0)
  const [publicError, setPublicError] = useState<string | null>(null)
  const [publicStatus, setPublicStatus] = useState<string | null>(null)
  const [publicJob, setPublicJob] = useState<PublicProcessingJob | null>(null)
  const [publicViewerItems, setPublicViewerItems] = useState<BrainViewerItem[]>([])
  const [publicViewerTitle, setPublicViewerTitle] = useState('3D preview')
  const [isPublicViewerReady, setIsPublicViewerReady] = useState(false)
  const [publicViewerVersion, setPublicViewerVersion] = useState(0)
  const publicObjectUrlsRef = useRef<string[]>([])

  useEffect(() => {
    return () => {
      publicObjectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    }
  }, [])

  function replacePublicViewerItems(viewerItems: BrainViewerItem[]) {
    publicObjectUrlsRef.current.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    publicObjectUrlsRef.current = viewerItems.map((item) => item.objectUrl)
    setPublicViewerItems(viewerItems)
    setPublicViewerVersion((current) => current + 1)
    setIsPublicViewerReady(viewerItems.length === 0)
  }

  async function waitForPublicJob(jobId: string): Promise<PublicProcessingJob> {
    for (;;) {
      const job = await getPublicProcessingJob(jobId)
      setPublicJob(job)
      setPublicProgress(Math.round(job.progress ?? 0))
      setPublicStatus(job.status === 'completed' ? 'Processing complete. Preparing the result files.' : 'Processing your MRI. Keep this page open until the result is ready.')

      if (job.status === 'completed') {
        return job
      }
      if (job.status === 'failed') {
        throw new Error(job.error || 'The MRI could not be processed.')
      }

      await new Promise((resolve) => window.setTimeout(resolve, 1000))
    }
  }

  async function handlePublicSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!publicFile) {
      setPublicError('Choose a .nii or .nii.gz MRI file first.')
      return
    }

    setIsPublicProcessing(true)
    setPublicProgress(1)
    setPublicError(null)
    setPublicStatus('Uploading your MRI. Processing will start automatically.')

    try {
      const startedJob = await startPublicProcessingJob(publicFile)
      setPublicJob(startedJob)
      setPublicProgress(Math.round(startedJob.progress ?? 2))
      setPublicStatus('Processing your MRI. Keep this page open until the result is ready.')

      const completedJob = await waitForPublicJob(startedJob.id)
      const blob = await downloadPublicProcessingResult(completedJob.id)
      const base = getBaseName(publicFile.name)
      const viewerItems = await extractViewerItemsFromPublicZip(blob)

      setPublicProgress(100)
      setPublicViewerTitle(`${base} preview`)
      replacePublicViewerItems(viewerItems)
      setPublicStatus('Processing complete. Your result download has started.')
      downloadBlob(blob, completedJob.download_filename || `${base}_brain_mri_results.zip`)
    } catch (error) {
      setPublicError(getFriendlyPublicError(error))
      setPublicStatus(null)
    } finally {
      setIsPublicProcessing(false)
    }
  }

  const showProgress = isPublicProcessing || publicProgress > 0
  const showViewerLoader = publicViewerItems.length > 0 && !isPublicViewerReady

  return (
    <main className="welcome-page clean-welcome-page public-home-page">
      <button type="button" className="top-auth-button" onClick={onOpenAuth}>
        Login / Sign up
      </button>

      <section className="welcome-landing-card public-hero-card">
        <p className="eyebrow">Brain MRI Processing</p>
        <h1>Turn MRI scans into 3D brain tissue results.</h1>
        <p className="hero-text">
          Upload a NIfTI MRI scan and receive a compact result package with 3D GLB models and a JSON measurements file.
          The public mode is designed for a quick one-time preview: no account is required, and the generated result is downloaded
          when processing is complete.
        </p>
        <div className="public-feature-strip" aria-label="Application capabilities">
          <span>3D tissue preview</span>
          <span>Volume and surface measurements</span>
          <span>Downloadable GLB and JSON results</span>
        </div>
      </section>

      <section className="page public-flow-section public-upload-section">
        <article className="card public-upload-card public-flow-card">
          <div>
            <p className="eyebrow">Process an MRI</p>
            <h2>Choose a scan file</h2>
            <p className="muted">
              Use a .nii or .nii.gz file. Keep this page open while the progress bar updates from the processing server.
            </p>
          </div>

          <form className="form-grid" onSubmit={handlePublicSubmit}>
            <label>
              MRI file
              <input
                type="file"
                accept=".nii,.gz,.nii.gz"
                onChange={(event) => {
                  setPublicFile(event.target.files?.[0] ?? null)
                  setPublicError(null)
                  if (!isPublicProcessing) {
                    setPublicStatus(null)
                    setPublicProgress(0)
                    setPublicJob(null)
                  }
                }}
                disabled={isPublicProcessing}
                required
              />
            </label>

            {showProgress && (
              <div className="public-progress-card" role="status" aria-live="polite">
                <div className="row-between">
                  <strong>{publicJob?.status === 'completed' ? 'Processing complete' : 'Processing MRI'}</strong>
                  <span>{Math.round(publicProgress)}%</span>
                </div>
                <div className="progress-wrap" aria-hidden="true">
                  <div className="progress-bar" style={{ width: `${publicProgress}%` }} />
                </div>
                {publicStatus && <p className="muted small-note">{publicStatus}</p>}
              </div>
            )}

            {publicError && <p className="error-text">{publicError}</p>}
            <button type="submit" disabled={isPublicProcessing}>
              {isPublicProcessing ? 'Processing...' : publicViewerItems.length > 0 ? 'Process another MRI' : 'Process MRI'}
            </button>
          </form>
        </article>
      </section>

      {showViewerLoader && (
        <section className="page public-flow-section public-viewer-spacer">
          <article className="card public-viewer-loading-card">
            <p className="eyebrow">3D preview</p>
            <h2>The 3D component is loading</h2>
            <p className="muted">The preview will appear as soon as the model is fully ready.</p>
          </article>
        </section>
      )}

      {publicViewerItems.length > 0 && (
        <section className={`page public-viewer-section public-viewer-spacer ${isPublicViewerReady ? '' : 'viewer-preload-hidden'}`}>
          <Suspense
            fallback={
              <section className="card public-viewer-loading-card">
                <p className="eyebrow">3D preview</p>
                <h2>The 3D component is loading</h2>
                <p className="muted">The preview will appear as soon as the model is fully ready.</p>
              </section>
            }
          >
            <Brain3DViewer
              key={publicViewerVersion}
              items={publicViewerItems}
              title={publicViewerTitle}
              subtitle="Preview the generated tissue models before opening the downloaded result files."
              loadingText="The 3D component is loading..."
              onSceneReady={() => setIsPublicViewerReady(true)}
            />
          </Suspense>
        </section>
      )}
    </main>
  )
}
