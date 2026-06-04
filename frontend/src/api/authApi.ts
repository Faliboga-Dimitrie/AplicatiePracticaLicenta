import { apiRequest, clearAccessToken, storeAccessToken } from './client'
import type { CurrentUserResponse, LoginResponse } from '../types/api'

function storeSession(session: LoginResponse): LoginResponse {
  storeAccessToken(session.access_token)
  return session
}

function requestSession(path: string, body?: { email: string; password: string }): Promise<LoginResponse> {
  return apiRequest<LoginResponse>(path, {
    method: 'POST',
    body,
    auth: false,
  }).then(storeSession)
}

export function register(email: string, password: string): Promise<LoginResponse> {
  return requestSession('/auth/register', { email, password })
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return requestSession('/auth/login', { email, password })
}

export async function getCurrentUser(): Promise<CurrentUserResponse> {
  return apiRequest<CurrentUserResponse>('/auth/me')
}

export function refreshSession(): Promise<LoginResponse> {
  return requestSession('/auth/refresh')
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

export async function deleteAccount(): Promise<{ deleted: boolean; deleted_subject_ids: string[]; kept_subject_ids: string[] }> {
  try {
    return await apiRequest<{ deleted: boolean; deleted_subject_ids: string[]; kept_subject_ids: string[] }>(
      '/auth/account',
      { method: 'DELETE' },
    )
  } finally {
    clearAccessToken()
  }
}
