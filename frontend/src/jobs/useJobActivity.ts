import { useContext } from 'react'
import { JobActivityContext } from './JobActivityContext'

export function useJobActivity() {
  const value = useContext(JobActivityContext)
  if (!value) {
    throw new Error('useJobActivity must be used inside JobActivityProvider')
  }
  return value
}
