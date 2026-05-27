import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest, deleteAccount as deleteAccountRequest, logoutAll as logoutAllRequest, refreshSession, register as registerRequest } from '../api/authApi'
import { apiMessage, clearAccessToken, getStoredAccessToken } from '../api/client'
import type { User } from '../types/api'

type AuthContextValue = {
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

type AuthProviderProps = {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [isCheckingSession, setIsCheckingSession] = useState(true)
  const [authError, setAuthError] = useState<string | null>(null)

  const clearAuthError = useCallback(() => {
    setAuthError(null)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setAuthError(null)
    const session = await loginRequest(email, password)
    setUser(session.user)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    setAuthError(null)
    const session = await registerRequest(email, password)
    setUser(session.user)
  }, [])

  const logout = useCallback(async () => {
    setAuthError(null)
    await logoutRequest()
    setUser(null)
  }, [])

  const logoutAll = useCallback(async () => {
    setAuthError(null)
    await logoutAllRequest()
    setUser(null)
  }, [])

  const deleteAccount = useCallback(async () => {
    setAuthError(null)
    await deleteAccountRequest()
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      setIsCheckingSession(true)
      setAuthError(null)

      try {
        if (!getStoredAccessToken()) {
          const refreshed = await refreshSession()
          if (!cancelled) {
            setUser(refreshed.user)
          }
          return
        }

        const current = await getCurrentUser()
        if (!cancelled) {
          setUser(current.user)
        }
      } catch (error) {
        clearAccessToken()
        if (!cancelled) {
          setUser(null)
          setAuthError(apiMessage(error))
        }
      } finally {
        if (!cancelled) {
          setIsCheckingSession(false)
        }
      }
    }

    restoreSession()

    return () => {
      cancelled = true
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isCheckingSession,
      authError,
      isAuthenticated: user !== null,
      login,
      register,
      logout,
      logoutAll,
      deleteAccount,
      clearAuthError,
    }),
    [authError, clearAuthError, isCheckingSession, login, register, logout, logoutAll, deleteAccount, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
