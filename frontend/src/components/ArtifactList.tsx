import { useState } from 'react'
import { apiMessage } from '../api/client'
import { downloadArtifact } from '../api/artifactsApi'
import type { Artifact } from '../types/api'

type ArtifactListProps = {
  artifacts: Artifact[]
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function friendlyArtifactName(artifact: Artifact): string {
  const lower = artifact.name.toLowerCase()
  if (lower.endsWith('.glb')) {
    if (lower.includes('gm') || lower.includes('gray')) return 'Grey matter 3D model'
    if (lower.includes('wm') || lower.includes('white')) return 'White matter 3D model'
    if (lower.includes('csf')) return 'CSF 3D model'
    return '3D model'
  }
  if (lower.endsWith('.csv')) {
    if (lower.includes('volume')) return 'Volume measurements table'
    if (lower.includes('surface')) return 'Surface measurements table'
    return 'Measurements table'
  }
  if (lower.endsWith('.json')) return 'Measurement data'
  if (lower.endsWith('.nii') || lower.endsWith('.nii.gz')) return 'MRI processing file'
  return artifact.name
}

function friendlyArtifactDescription(artifact: Artifact): string {
  const lower = artifact.name.toLowerCase()
  if (lower.endsWith('.glb')) return `3D file · ${formatBytes(artifact.size_bytes)}`
  if (lower.endsWith('.csv')) return `Spreadsheet-friendly file · ${formatBytes(artifact.size_bytes)}`
  if (lower.endsWith('.json')) return `Structured data file · ${formatBytes(artifact.size_bytes)}`
  return `${artifact.name} · ${formatBytes(artifact.size_bytes)}`
}

export function ArtifactList({ artifacts }: ArtifactListProps) {
  const [downloadingName, setDownloadingName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload(artifact: Artifact) {
    setDownloadingName(artifact.name)
    setError(null)
    try {
      await downloadArtifact(artifact)
    } catch (downloadError) {
      setError(apiMessage(downloadError))
    } finally {
      setDownloadingName(null)
    }
  }

  if (artifacts.length === 0) {
    return <p className="muted">No result files are available yet. Create the 3D model and measurements first.</p>
  }

  return (
    <div className="stack">
      {error && <p className="error-text">{error}</p>}
      <div className="table-like download-list">
        {artifacts.map((artifact) => (
          <div className="table-row" key={`${artifact.kind}-${artifact.name}`}>
            <div>
              <strong>{friendlyArtifactName(artifact)}</strong>
              <p className="muted">{friendlyArtifactDescription(artifact)}</p>
            </div>
            <button
              type="button"
              className="secondary"
              onClick={() => handleDownload(artifact)}
              disabled={downloadingName === artifact.name}
            >
              {downloadingName === artifact.name ? 'Downloading...' : 'Download'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
