import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { AgentHopState } from './types'

const state: AgentHopState = {
  providers: [{ id: 'codex', name: 'Codex', available: true }],
  accounts: [
    { provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, usage: { plan: 'Plus', fiveHourUsed: 32, fiveHourResetsAt: 2_000_000_000, weeklyUsed: 61, status: 'ready' } },
    { provider: 'codex', id: 'personal', active: false, authenticated: true, duplicate: false, usage: { fiveHourUsed: 7, weeklyUsed: 19, status: 'ready' } },
  ],
  sessions: [{ provider: 'codex', id: 'session-1', title: 'Build account switcher', updatedAt: Math.floor(Date.now() / 1000) }],
  recommendation: { provider: 'codex', account: 'personal', reason: 'Most capacity available' },
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows accounts, recommendation, and usage without a session list', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(state))
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pick up where you left off.' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'AgentHop mascot meditating while companion agents work around it' })).toHaveAttribute('src', '/assets/agenthop-mascot.png')
    expect(screen.getByRole('link', { name: 'AgentHop home' }).querySelector('img')).toHaveAttribute('src', '/assets/agenthop-mascot.png')
    expect(fetchMock).toHaveBeenCalledWith('/api/refresh', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByRole('heading', { name: 'work' })).toBeInTheDocument()
    expect(screen.getByText('Best choice')).toBeInTheDocument()
    expect(screen.queryByText('Most capacity available')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh usage' })).toBeInTheDocument()
    expect(screen.queryByText('Account control center')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Recent sessions' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')).toHaveLength(4)
    expect(screen.queryByText(/1970/)).not.toBeInTheDocument()
  })

  it('does not imply full capacity when live usage is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false }],
    }))
    render(<App />)

    expect(await screen.findByLabelText('Account state: unknown')).toHaveTextContent(/unknown/i)
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('shows account state separately from the 5-hour and weekly limits', async () => {
    const now = Math.floor(Date.now() / 1000)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, usage: { fiveHourUsed: 0, fiveHourResetsAt: now + 5 * 3_600 + 30 * 60, weeklyUsed: 100, weeklyResetsAt: now + 2 * 86_400 + 3 * 3_600, status: 'blocked' } }],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByLabelText('Account state: blocked')).toHaveTextContent(/blocked/i)
    expect(screen.getByText('5-hour limit')).toBeInTheDocument()
    expect(screen.getByText('Weekly limit')).toBeInTheDocument()
    expect(screen.getByText('100% left')).toBeInTheDocument()
    expect(screen.getByText('0% left')).toBeInTheDocument()
    expect(screen.getByText('Resets in 5h 30m')).toBeInTheDocument()
    expect(screen.getByText('Resets in 2d 3h')).toBeInTheDocument()
    expect(screen.getByText('Expected unblock in 2d 3h')).toBeInTheDocument()
    expect(screen.queryByLabelText(/percent remaining/)).not.toBeInTheDocument()
  })

  it('uses the 5-hour reset when weekly capacity remains', async () => {
    const now = Math.floor(Date.now() / 1000)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, usage: { fiveHourUsed: 100, fiveHourResetsAt: now + 90 * 60, weeklyUsed: 40, weeklyResetsAt: now + 3 * 86_400, status: 'blocked' } }],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByText('Expected unblock in 1h 30m')).toBeInTheDocument()
  })

  it('waits for the later reset when both limits are exhausted', async () => {
    const now = Math.floor(Date.now() / 1000)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, usage: { fiveHourUsed: 100, fiveHourResetsAt: now + 60 * 60, weeklyUsed: 100, weeklyResetsAt: now + 2 * 86_400, status: 'blocked' } }],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByText('Expected unblock in 2d 0h')).toBeInTheDocument()
  })

  it('falls back to legacy clipboard copying when the Clipboard API is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ command: 'codex new' }))
    const execCommand = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand })
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: /start new session/i }))
    await userEvent.click(await screen.findByRole('button', { name: 'Copy command' }))

    expect(execCommand).toHaveBeenCalledWith('copy')
    expect(screen.getByText('Copied')).toBeInTheDocument()
  })

  it('switches accounts and reloads state', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'personal', active: true }))
      .mockResolvedValueOnce(json(state))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: /switch to account/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/providers/codex/accounts/personal/activate', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenNthCalledWith(3, '/api/refresh', expect.objectContaining({ method: 'POST' }))
  })

  it('creates a profile and presents the browser-login command without collecting credentials', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'account-05', command: 'CODEX_HOME=/profiles/account-05 codex login' }, 201))
      .mockResolvedValueOnce(json(state))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Add account' }))
    const nameInput = screen.getByLabelText('New account name')
    expect(screen.queryByLabelText(/password|token/i)).not.toBeInTheDocument()
    await userEvent.type(nameInput, 'account-05')
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByRole('dialog')).toHaveTextContent('Connect account-05')
    expect(screen.getByLabelText('Terminal command')).toHaveTextContent('CODEX_HOME=/profiles/account-05 codex login')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/providers/codex/accounts', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ account: 'account-05' }),
    }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
  })

  it('cancels profile creation without sending a request and clears the entered name', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(state))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Add account' }))
    await userEvent.type(screen.getByLabelText('New account name'), 'account-05')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByLabelText('New account name')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: 'Add account' }))
    expect(screen.getByLabelText('New account name')).toHaveValue('')
  })

  it('keeps a successful profile creation visible when the follow-up refresh fails', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'account-05', command: 'CODEX_HOME=/profiles/account-05 codex login' }, 201))
      .mockResolvedValueOnce(json({ detail: 'Refresh is temporarily unavailable' }, 503))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Add account' }))
    await userEvent.type(screen.getByLabelText('New account name'), 'account-05')
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByRole('dialog')).toHaveTextContent('Connect account-05')
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh is temporarily unavailable')
    expect(screen.queryByText('Could not add the account.')).not.toBeInTheDocument()
  })
})
