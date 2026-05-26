import { apiRequest, clearAccessToken, storeAccessToken } from './client'
import type { CurrentUserResponse, LoginResponse } from '../types/api'

export async function register(email: string, password: string): Promise<LoginResponse> {
  const session = await apiRequest<LoginResponse>('/auth/register', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
  storeAccessToken(session.access_token, session.expires_at)
  return session
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const session = await apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  })
  storeAccessToken(session.access_token, session.expires_at)
  return session
}

export async function getCurrentUser(): Promise<CurrentUserResponse> {
  return apiRequest<CurrentUserResponse>('/auth/me')
}

export async function refreshSession(): Promise<LoginResponse> {
  const session = await apiRequest<LoginResponse>('/auth/refresh', {
    method: 'POST',
    auth: false,
  })
  storeAccessToken(session.access_token, session.expires_at)
  return session
}

export async function logout(): Promise<void> {
  try {
    await apiRequest<{ logged_out: boolean }>('/auth/logout', {
      method: 'POST',
      auth: false,
    })
  } finally {
    clearAccessToken()
  }
}

export async function logoutAll(): Promise<void> {
  try {
    await apiRequest<{ logged_out: boolean; all_sessions: boolean }>('/auth/logout-all', {
      method: 'POST',
    })
  } finally {
    clearAccessToken()
  }
}
