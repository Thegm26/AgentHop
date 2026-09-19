import type { AgentHopState, CommandMode } from './types'

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, {
    ...init,
    headers,
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: unknown; message?: unknown }
      if (typeof body.detail === 'string') message = body.detail
      else if (typeof body.message === 'string') message = body.message
    } catch {
      // Keep the useful status-based fallback for non-JSON errors.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  getState: () => request<AgentHopState>('/api/state'),
  refresh: () => request<AgentHopState>('/api/refresh', { method: 'POST' }),
  onboard: (providerId: string, account: string) =>
    request<{ provider: string; account: string; command: string }>(
      `/api/providers/${encodeURIComponent(providerId)}/accounts`,
      { method: 'POST', body: JSON.stringify({ account }) },
    ),
  activate: (providerId: string, accountId: string) =>
    request<{ provider: string; account: string; active: boolean }>(
      `/api/providers/${encodeURIComponent(providerId)}/accounts/${encodeURIComponent(accountId)}/activate`,
      { method: 'POST' },
    ),
  command: (providerId: string, accountId: string, mode: CommandMode, sessionId?: string) =>
    request<{ command: string }>(
      `/api/providers/${encodeURIComponent(providerId)}/accounts/${encodeURIComponent(accountId)}/command`,
      { method: 'POST', body: JSON.stringify({ mode, ...(sessionId ? { sessionId } : {}) }) },
    ),
}

export { ApiError }
