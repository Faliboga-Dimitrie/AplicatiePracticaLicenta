import type { ApiErrorPayload, LoginResponse } from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const ACCESS_TOKEN_KEY = 'mri_access_token'

class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function getStoredAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function storeAccessToken(accessToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
}

type ApiRequestOptions = {
  method?: string
  body?: unknown
  formData?: FormData
  headers?: Record<string, string>
  auth?: boolean
  retryOnUnauthorized?: boolean
}

function buildUrl(path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path
  }
  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

async function readError(response: Response): Promise<ApiError> {
  const fallbackMessage = response.statusText || 'Request failed.'

  try {
    const payload = (await response.json()) as Partial<ApiErrorPayload>
    const error = payload.error
    if (error) {
      return new ApiError(
        response.status,
        error.code || `HTTP_${response.status}`,
        error.message || fallbackMessage,
        error.details,
      )
    }
  } catch {
    // Fall through to generic error.
  }

  return new ApiError(response.status, `HTTP_${response.status}`, fallbackMessage)
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }

  return (await response.text()) as T
}

async function refreshAccessToken(): Promise<LoginResponse> {
  const response = await fetch(buildUrl('/auth/refresh'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    clearAccessToken()
    throw await readError(response)
  }

  const session = await parseResponse<LoginResponse>(response)
  storeAccessToken(session.access_token)
  return session
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const {
    method = options.body || options.formData ? 'POST' : 'GET',
    body,
    formData,
    headers = {},
    auth = true,
    retryOnUnauthorized = true,
  } = options

  const requestHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  }

  let requestBody: BodyInit | undefined
  if (formData) {
    requestBody = formData
  } else if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }

  const token = getStoredAccessToken()
  if (auth && token) {
    requestHeaders.Authorization = `Bearer ${token}`
  }

  const response = await fetch(buildUrl(path), {
    method,
    headers: requestHeaders,
    body: requestBody,
    credentials: 'include',
  })

  if (response.status === 401 && auth && retryOnUnauthorized) {
    await refreshAccessToken()
    return apiRequest<T>(path, {
      method,
      body,
      formData,
      headers,
      auth,
      retryOnUnauthorized: false,
    })
  }

  if (!response.ok) {
    throw await readError(response)
  }

  return parseResponse<T>(response)
}

export async function apiDownload(path: string): Promise<Blob> {
  const response = await fetch(buildUrl(path), {
    method: 'GET',
    credentials: 'include',
    headers: {
      Authorization: `Bearer ${getStoredAccessToken() ?? ''}`,
    },
  })

  if (response.status === 401) {
    await refreshAccessToken()
    return apiDownload(path)
  }

  if (!response.ok) {
    throw await readError(response)
  }

  return response.blob()
}

export async function apiPublicDownload(
  path: string,
  options: { method?: string; formData?: FormData } = {},
): Promise<Blob> {
  const response = await fetch(buildUrl(path), {
    method: options.method ?? 'GET',
    body: options.formData,
    credentials: 'include',
  })

  if (!response.ok) {
    throw await readError(response)
  }

  return response.blob()
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Unexpected error.'
}
