import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('api', () => {
  afterEach(() => vi.restoreAllMocks())

  it('encodes account paths and sends the command payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ command: 'codex resume abc' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await expect(api.command('open ai', 'work/account', 'resume', 'abc')).resolves.toEqual({ command: 'codex resume abc' })
    expect(fetchMock).toHaveBeenCalledWith('/api/providers/open%20ai/accounts/work%2Faccount/command', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ mode: 'resume', sessionId: 'abc' }),
    }))
  })

  it('surfaces backend error details', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'Account is unavailable' }), { status: 409, headers: { 'Content-Type': 'application/json' } }))

    await expect(api.activate('codex', 'account-2')).rejects.toEqual(expect.objectContaining({ message: 'Account is unavailable', status: 409 }))
  })

  it('does not leak structured validation details into a renderable error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: 'invalid' }] }), { status: 422, headers: { 'Content-Type': 'application/json' } }))

    await expect(api.refresh()).rejects.toEqual(expect.objectContaining({ message: 'Request failed (422)' }))
  })
})
