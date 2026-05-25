import { useState } from 'react'
import { apiMessage } from '../api/client'
import { downloadArtifact } from '../api/artifactsApi'
import type { Artifact } from '../types/api'

type ArtifactListProps = {
  artifacts: Artifact[]
}

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
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
    return <p className="muted">No artifacts are available for this case yet.</p>
  }

  return (
    <div className="stack">
      {error && <p className="error-text">{error}</p>}
      <div className="table-like">
        {artifacts.map((artifact) => (
          <div className="table-row" key={`${artifact.kind}-${artifact.name}`}>
            <div>
              <strong>{artifact.name}</strong>
              <p className="muted">{artifact.kind} · {artifact.mime_type || 'unknown type'} · {formatBytes(artifact.size_bytes)}</p>
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
