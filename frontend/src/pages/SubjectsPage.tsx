import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { createSubject, listSubjects } from '../api/subjectsApi'
import type { AuthorizedSubject } from '../types/api'

type SubjectsPageProps = {
  onSelectSubject: (subjectId: string) => void
}

export function SubjectsPage({ onSelectSubject }: SubjectsPageProps) {
  const [subjects, setSubjects] = useState<AuthorizedSubject[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [subjectId, setSubjectId] = useState('')
  const [name, setName] = useState('')
  const [age, setAge] = useState('')
  const [notes, setNotes] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  async function refreshSubjects() {
    setIsLoading(true)
    setError(null)
    try {
      const loadedSubjects = await listSubjects()
      setSubjects(loadedSubjects)
    } catch (loadError) {
      setError(apiMessage(loadError))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    refreshSubjects()
  }, [])

  async function handleCreateSubject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsCreating(true)
    setError(null)
    try {
      await createSubject({
        subject_id: subjectId.trim(),
        name: name.trim() || null,
        age: age ? Number(age) : null,
        notes: notes.trim() || null,
      })
      setSubjectId('')
      setName('')
      setAge('')
      setNotes('')
      await refreshSubjects()
    } catch (createError) {
      setError(apiMessage(createError))
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <main className="page two-column">
      <section className="stack">
        <div className="row-between">
          <div>
            <p className="eyebrow">Step 1</p>
            <h1>Subjects</h1>
          </div>
          <button type="button" className="secondary" onClick={refreshSubjects} disabled={isLoading}>
            Refresh
          </button>
        </div>

        {error && <p className="error-text">{error}</p>}
        {isLoading && <p className="muted">Loading subjects...</p>}

        {!isLoading && subjects.length === 0 && (
          <p className="muted">No authorized subjects yet. Create one from the form.</p>
        )}

        <div className="card-list">
          {subjects.map((subject) => (
            <button
              type="button"
              className="card clickable-card"
              key={subject.id}
              onClick={() => onSelectSubject(subject.id)}
            >
              <div className="row-between">
                <strong>{subject.id}</strong>
                <span className="badge">{subject.role}</span>
              </div>
              <p className="muted">{subject.name || 'No display name'} · {subject.case_count} case(s)</p>
              {subject.notes && <p>{subject.notes}</p>}
            </button>
          ))}
        </div>
      </section>

      <aside>
        <form className="card form-grid" onSubmit={handleCreateSubject}>
          <h2>Create subject</h2>
          <label>
            Subject ID
            <input value={subjectId} onChange={(event) => setSubjectId(event.target.value)} required />
          </label>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Age
            <input type="number" min="0" value={age} onChange={(event) => setAge(event.target.value)} />
          </label>
          <label>
            Notes
            <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} />
          </label>
          <button type="submit" disabled={isCreating}>
            {isCreating ? 'Creating...' : 'Create subject'}
          </button>
        </form>
      </aside>
    </main>
  )
}
