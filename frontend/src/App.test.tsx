import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { AgentHopState } from './types'

const state: AgentHopState = {
  providers: [{ id: 'codex', name: 'Codex', available: true }],
  accounts: [
    { provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, email: 'work@example.com', usage: { plan: 'Plus', fiveHourUsed: 32, fiveHourResetsAt: 2_000_000_000, weeklyUsed: 61, status: 'ready' } },
    { provider: 'codex', id: 'personal', active: false, authenticated: true, duplicate: false, usage: { plan: 'Plus', fiveHourUsed: 7, weeklyUsed: 19, status: 'ready' } },
  ],
  sessions: [{ provider: 'codex', id: 'session-1', title: 'Build account switcher', updatedAt: Math.floor(Date.now() / 1000) }],
  recommendation: { provider: 'codex', account: 'personal', reason: 'Available profile' },
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('shows accounts, a suggested profile, and usage without a session list', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(state))
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pick up where you left off.' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'AgentHop mascot meditating while companion agents work around it' })).toHaveAttribute('src', '/assets/agenthop-mascot.png')
    expect(screen.getByRole('link', { name: 'AgentHop home' })).toHaveTextContent('AgentHop')
    expect(screen.getByRole('link', { name: 'AgentHop home' }).querySelector('img')).toBeNull()
    expect(fetchMock).toHaveBeenCalledWith('/api/refresh', expect.objectContaining({ method: 'POST' }))
    expect(screen.getByRole('heading', { name: 'work' })).toBeInTheDocument()
    expect(screen.getByText('work@example.com')).toBeInTheDocument()
    expect(screen.queryByText('Active')).not.toBeInTheDocument()
    expect(screen.getByText('Suggested profile')).toBeInTheDocument()
    expect(screen.queryByText('Available profile')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh usage & resets' })).toBeInTheDocument()
    expect(screen.queryByText('Account control center')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Recent sessions' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('progressbar')).toHaveLength(4)
    expect(screen.queryByText(/1970/)).not.toBeInTheDocument()
  })

  it('renders account cards directly when accounts have one category', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(state))
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'work' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'personal' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Account categories')).not.toBeInTheDocument()
  })

  it('keeps every account card visible initially and lets categories filter them', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [
        { provider: 'codex', id: 'default', active: true, authenticated: false, duplicate: false },
        { provider: 'codex', id: 'account-05', active: false, authenticated: false, duplicate: false },
        { provider: 'codex', id: 'account-01', active: false, authenticated: true, duplicate: false, usage: { plan: 'Plus', status: 'blocked' } },
        { provider: 'codex', id: 'personal', active: false, authenticated: true, duplicate: false, usage: { plan: 'Free', status: 'ready' } },
      ],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByLabelText('Account categories')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'default' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'account-05' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'account-01' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'personal' })).toBeInTheDocument()
    expect(screen.getAllByLabelText('Account state: disconnected')).toHaveLength(2)
    expect(screen.getAllByText('No email connected')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Clean unavailable/i })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Plus (1)' }))

    expect(screen.getByRole('heading', { name: 'account-01' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'default' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'personal' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'All accounts' }))
    await userEvent.click(screen.getByRole('button', { name: 'Personal (1)' }))

    expect(screen.getByRole('heading', { name: 'personal' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'default' })).not.toBeInTheDocument()
  })

  it('keeps the selected category open when refreshed state retains it', async () => {
    const categorizedState = {
      ...state,
      accounts: [
        { provider: 'codex', id: 'default', active: true, authenticated: true, duplicate: false, usage: { plan: 'Plus', status: 'ready' } },
        { provider: 'codex', id: 'personal', active: false, authenticated: true, duplicate: false, usage: { plan: 'Free', status: 'ready' } },
      ],
      recommendation: null,
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(categorizedState))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Plus (1)' }))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh usage & resets' }))

    expect(await screen.findByRole('heading', { name: 'default' })).toBeInTheDocument()
    expect(screen.getByLabelText('Account categories')).toBeInTheDocument()
  })

  it('polls every five seconds without overlapping requests and stops when unmounted', async () => {
    vi.useFakeTimers()
    let resolveRefresh: ((response: Response) => void) | undefined
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockImplementation(() => new Promise<Response>((resolve) => {
        resolveRefresh = resolve
      }))
    const { unmount } = render(<App />)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(0)
    expect(screen.getByRole('button', { name: 'Refresh usage & resets' })).toBeInTheDocument()

    await vi.advanceTimersByTimeAsync(5_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    resolveRefresh?.(json(state))
    await vi.advanceTimersByTimeAsync(0)

    unmount()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
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

  it('uses a neutral email fallback for authenticated non-ChatGPT accounts', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'api-key', active: true, authenticated: true, duplicate: false, usage: { status: 'ready' } }],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByText('Email unavailable')).toBeInTheDocument()
    expect(screen.getByText('Connected account')).toBeInTheDocument()
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
    expect(screen.queryByText('Usage & resets')).not.toBeInTheDocument()
    expect(screen.queryByText('Reported by Codex')).not.toBeInTheDocument()
    expect(screen.getByText('5-hour limit')).toBeInTheDocument()
    expect(screen.getByText('Weekly limit')).toBeInTheDocument()
    expect(screen.getAllByText('Remaining')).toHaveLength(2)
    expect(screen.getAllByRole('progressbar')).toHaveLength(2)
    expect(screen.getByRole('progressbar', { name: '5-hour limit remaining capacity' })).toHaveAttribute('aria-valuenow', '100')
    expect(screen.getByRole('progressbar', { name: 'Weekly limit remaining capacity' })).toHaveAttribute('aria-valuenow', '0')
    expect(screen.getByRole('progressbar', { name: '5-hour limit remaining capacity' })).toHaveClass('capacity-bar--healthy')
    expect(screen.getByRole('progressbar', { name: 'Weekly limit remaining capacity' })).toHaveClass('capacity-bar--exhausted')
    expect(screen.getByText('0%')).toBeInTheDocument()
    expect(screen.getAllByText('Reset')).toHaveLength(2)
    expect(screen.getByText(/\(in 5h 30m\)/)).toBeInTheDocument()
    expect(screen.getByText(/\(in 2d 3h\)/)).toBeInTheDocument()
    expect(screen.getAllByRole('time')).toHaveLength(2)
    expect(screen.getByText('Expected unblock in 2d 3h')).toBeInTheDocument()
    expect(screen.getByLabelText('5-hour limit remaining capacity and reset details')).toBeInTheDocument()
  })

  it('keeps a profile usable when Codex reports a false ordinary-usage flag but its windows have capacity', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({
      ...state,
      accounts: [{ provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false, usage: { fiveHourUsed: 32, weeklyUsed: 75, allowed: false, status: 'ready' } }],
      recommendation: null,
    }))
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'work' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Start new session/i })).not.toBeInTheDocument()
    expect(screen.getByText('68%')).toBeInTheDocument()
    expect(screen.getByText('25%')).toBeInTheDocument()
  })

  it('redeems an available usage-limit reset only after confirmation', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const creditState = {
      ...state,
      accounts: [{ ...state.accounts[0], usage: { ...state.accounts[0].usage, resetCreditsAvailable: 1 } }],
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(creditState))
      .mockResolvedValueOnce(json({ outcome: 'reset' }))
      .mockResolvedValueOnce(json({ ...creditState, accounts: [{ ...creditState.accounts[0], usage: { ...creditState.accounts[0].usage, resetCreditsAvailable: 0 } }] }))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Redeem usage limit reset (1)' }))

    expect(confirm).toHaveBeenCalledWith('Redeem usage limit reset? You have 1 usage limit reset available.')
    expect(fetchMock).toHaveBeenCalledWith('/api/providers/codex/accounts/work/reset-credit/redeem', expect.objectContaining({ method: 'POST' }))
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

  it('switches accounts and reloads state', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'personal', active: true }))
      .mockResolvedValueOnce(json(state))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: /switch to this/i }))

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

  it('uses a generated name when a profile is created without one', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(state))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'account-03', command: 'CODEX_HOME=/profiles/account-03 codex login' }, 201))
      .mockResolvedValueOnce(json(state))
    render(<App />)

    await userEvent.click(await screen.findByRole('button', { name: 'Add account' }))
    await userEvent.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(await screen.findByRole('dialog')).toHaveTextContent('Connect account-03')
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/providers/codex/accounts', expect.objectContaining({ body: JSON.stringify({ account: '' }) }))
  })

  it('confirms before deleting the default profile or inactive unusable profiles', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const unusableState = {
      ...state,
      accounts: [
        { provider: 'codex', id: 'default', active: false, authenticated: false, duplicate: false },
        { provider: 'codex', id: 'account-03', active: false, authenticated: true, duplicate: false, usage: { status: 'error' as const } },
        { provider: 'codex', id: 'active-error', active: true, authenticated: true, duplicate: false, usage: { status: 'error' as const } },
      ],
      recommendation: null,
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(unusableState))
      .mockResolvedValueOnce(json({ provider: 'codex', account: 'default', removed: true }))
      .mockResolvedValueOnce(json({ ...unusableState, accounts: [unusableState.accounts[0], unusableState.accounts[2]] }))
    render(<App />)

    await userEvent.click((await screen.findAllByRole('button', { name: 'Delete profile' }))[0])

    expect(confirm).toHaveBeenCalledWith('Delete the default profile? Its Codex credentials and configuration will be removed; sessions and shared state will stay on disk.')
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/providers/codex/accounts/default', expect.objectContaining({ method: 'DELETE' })))
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
