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

  it('shows accounts, recommendation, usage, and recent sessions', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(state))
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pick up where you left off.' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/refresh', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByRole('heading', { name: 'work' })).toBeInTheDocument()
    expect(screen.getByText('Best choice')).toBeInTheDocument()
    expect(screen.getByText('Build account switcher')).toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')).toHaveLength(4)
    expect(screen.queryByText(/1970/)).not.toBeInTheDocument()
  })

  it('does not imply full capacity when live usage is unavailable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false }],
    }))
    render(<App />)

    expect(await screen.findByRole('img', { name: 'Usage unavailable' })).toHaveTextContent('—')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('requests a resume command and presents a copyable dialog', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ command: 'codex-auto resume session-1' }))
    render(<App />)

    const resumeButton = await screen.findByRole('button', { name: /resume/i })
    await userEvent.click(resumeButton)

    expect(await screen.findByRole('dialog', { name: 'Resume Build account switcher' })).toHaveTextContent('codex-auto resume session-1')
    expect(screen.getByRole('button', { name: 'Close command dialog' })).toHaveFocus()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/providers/codex/accounts/work/command', expect.objectContaining({
      body: JSON.stringify({ mode: 'resume', sessionId: 'session-1' }),
    }))
    await userEvent.click(screen.getByRole('button', { name: 'Close command dialog' }))
    expect(resumeButton).toHaveFocus()
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
})
