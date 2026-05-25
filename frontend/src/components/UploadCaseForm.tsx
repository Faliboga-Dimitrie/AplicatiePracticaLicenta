import { useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { uploadCase } from '../api/casesApi'
import type { MriCase } from '../types/api'

type UploadCaseFormProps = {
  subjectId: string
  onCreated: (createdCase: MriCase) => void
}

export function UploadCaseForm({ subjectId, onCreated }: UploadCaseFormProps) {
  const [acquisitionDate, setAcquisitionDate] = useState('')
  const [notes, setNotes] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget

    if (!file) {
      setError('Choose a .nii or .nii.gz file first.')
      return
    }

    setIsUploading(true)
    setError(null)
    try {
      const response = await uploadCase({
        subjectId,
        acquisitionDate,
        notes: notes.trim() || undefined,
        file,
      })
      onCreated(response.case)
      setAcquisitionDate('')
      setNotes('')
      setFile(null)
      form.reset()
    } catch (uploadError) {
      setError(apiMessage(uploadError))
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <form className="card form-grid" onSubmit={handleSubmit}>
      <h3>Upload MRI case</h3>
      <label>
        Acquisition date
        <input
          type="date"
          value={acquisitionDate}
          onChange={(event) => setAcquisitionDate(event.target.value)}
          required
        />
      </label>
      <label>
        Notes
        <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} />
      </label>
      <label>
        Raw MRI file
        <input
          type="file"
          accept=".nii,.gz,.nii.gz"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          required
        />
      </label>
      {error && <p className="error-text">{error}</p>}
      <button type="submit" disabled={isUploading}>
        {isUploading ? 'Uploading...' : 'Upload case'}
      </button>
    </form>
  )
}
