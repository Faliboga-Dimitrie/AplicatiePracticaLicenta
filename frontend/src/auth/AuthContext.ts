import { createContext } from 'react'
import type { User } from '../types/api'

export type AuthContextValue = {
  user: User | null
  isCheckingSession: boolean
  authError: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  logoutAll: () => Promise<void>
  deleteAccount: () => Promise<void>
  clearAuthError: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
