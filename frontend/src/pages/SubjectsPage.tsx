import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { apiMessage } from '../api/client'
import { createSubject, deleteSubject, listSubjects, updateSubject } from '../api/subjectsApi'
import type { AuthorizedSubject } from '../types/api'

type SubjectsPageProps = {
  onSelectSubject: (subjectId: string) => void
}

type SubjectEditorState = {
  id: string
  name: string
  age: string
  notes: string
}

function toEditorState(subject: AuthorizedSubject): SubjectEditorState {
  return {
    id: subject.id,
    name: subject.name ?? '',
    age: subject.age === null || subject.age === undefined ? '' : String(subject.age),
    notes: subject.notes ?? '',
  }
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
  const [editingSubject, setEditingSubject] = useState<SubjectEditorState | null>(null)
  const [isUpdating, setIsUpdating] = useState(false)
  const [deletingSubjectId, setDeletingSubjectId] = useState<string | null>(null)

  const totalCases = useMemo(
    () => subjects.reduce((total, subject) => total + subject.case_count, 0),
    [subjects],
  )

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

  async function handleUpdateSubject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingSubject) {
      return
    }

    setIsUpdating(true)
    setError(null)
    try {
      await updateSubject(editingSubject.id, {
        name: editingSubject.name.trim() || null,
        age: editingSubject.age ? Number(editingSubject.age) : null,
        notes: editingSubject.notes.trim() || null,
      })
      setEditingSubject(null)
      await refreshSubjects()
    } catch (updateError) {
      setError(apiMessage(updateError))
    } finally {
      setIsUpdating(false)
    }
  }

  async function handleDeleteSubject(subject: AuthorizedSubject) {
    const confirmed = window.confirm(
      `Delete subject ${subject.id}? This also deletes its MRI cases and local workspace files.`,
    )
    if (!confirmed) {
      return
    }

    setDeletingSubjectId(subject.id)
    setError(null)
    try {
      await deleteSubject(subject.id)
      if (editingSubject?.id === subject.id) {
        setEditingSubject(null)
      }
      setSubjects((current) => current.filter((item) => item.id !== subject.id))
    } catch (deleteError) {
      setError(apiMessage(deleteError))
    } finally {
      setDeletingSubjectId(null)
    }
  }

  return (
    <main className="page stack">
      <section className="page-header-card">
        <div>
          <p className="eyebrow">Persistent workspace</p>
          <h1>Subjects & case ownership</h1>
          <p className="muted">
            Create, edit and delete subjects that belong to your account. A subject is the root container
            for dated MRI acquisitions.
          </p>
        </div>
        <button type="button" className="secondary" onClick={refreshSubjects} disabled={isLoading}>
          Refresh
        </button>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span>Visible subjects</span>
          <strong>{subjects.length}</strong>
        </article>
        <article className="metric-card">
          <span>Total cases</span>
          <strong>{totalCases}</strong>
        </article>
        <article className="metric-card">
          <span>Editable subjects</span>
          <strong>{subjects.filter((subject) => ['editor', 'admin', 'owner'].includes(subject.role)).length}</strong>
        </article>
      </section>

      <section className="two-column">
        <div className="stack">
          {error && <p className="error-text">{error}</p>}
          {isLoading && <p className="muted">Loading subjects...</p>}

          {!isLoading && subjects.length === 0 && (
            <article className="card empty-state">
              <h2>No subjects yet</h2>
              <p className="muted">Create your first subject from the form on the right.</p>
            </article>
          )}

          <div className="card-list">
            {subjects.map((subject) => (
              <article className="card subject-card" key={subject.id}>
                <div className="row-between">
                  <div>
                    <h2>{subject.id}</h2>
                    <p className="muted">
                      {subject.name || 'No display name'} · {subject.case_count} case(s)
                    </p>
                  </div>
                  <span className="badge">{subject.role}</span>
                </div>

                {subject.age !== null && <p className="muted">Age: {subject.age}</p>}
                {subject.notes && <p>{subject.notes}</p>}

                <div className="button-row">
                  <button type="button" onClick={() => onSelectSubject(subject.id)}>
                    Open cases
                  </button>
                  <button type="button" className="secondary" onClick={() => setEditingSubject(toEditorState(subject))}>
                    Edit subject
                  </button>
                  <button
                    type="button"
                    className="danger-button"
                    onClick={() => handleDeleteSubject(subject)}
                    disabled={deletingSubjectId === subject.id}
                  >
                    {deletingSubjectId === subject.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>

        <aside className="stack">
          <form className="card form-grid" onSubmit={handleCreateSubject}>
            <div>
              <p className="eyebrow">Create</p>
              <h2>New subject</h2>
            </div>
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

          {editingSubject && (
            <form className="card form-grid" onSubmit={handleUpdateSubject}>
              <div className="row-between">
                <div>
                  <p className="eyebrow">Edit</p>
                  <h2>{editingSubject.id}</h2>
                </div>
                <button type="button" className="secondary" onClick={() => setEditingSubject(null)}>
                  Cancel
                </button>
              </div>
              <label>
                Name
                <input
                  value={editingSubject.name}
                  onChange={(event) => setEditingSubject({ ...editingSubject, name: event.target.value })}
                />
              </label>
              <label>
                Age
                <input
                  type="number"
                  min="0"
                  value={editingSubject.age}
                  onChange={(event) => setEditingSubject({ ...editingSubject, age: event.target.value })}
                />
              </label>
              <label>
                Notes
                <textarea
                  value={editingSubject.notes}
                  onChange={(event) => setEditingSubject({ ...editingSubject, notes: event.target.value })}
                  rows={4}
                />
              </label>
              <button type="submit" disabled={isUpdating}>
                {isUpdating ? 'Saving...' : 'Save subject changes'}
              </button>
            </form>
          )}
        </aside>
      </section>
    </main>
  )
}
