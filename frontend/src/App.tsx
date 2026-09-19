import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { AccountCard } from './components/AccountCard'
import { CommandModal } from './components/CommandModal'
import { ArrowIcon, ClockIcon, RefreshIcon, SparkIcon, TerminalIcon } from './components/Icons'
import type { Account, AgentHopState, CommandMode, Session } from './types'

type ModalState = { command: string; title: string } | null

function relativeTime(value?: number | null) {
  if (value == null) return 'Recently'
  const timestamp = value < 1_000_000_000_000 ? value * 1000 : value
  if (!Number.isFinite(timestamp)) return 'Recently'
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000))
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function LoadingView() {
  return (
    <main className="main" aria-busy="true" aria-label="Loading AgentHop">
      <div className="skeleton skeleton--title" />
      <div className="account-grid">
        {[0, 1, 2].map((item) => <div className="skeleton skeleton--card" key={item} />)}
      </div>
    </main>
  )
}

function SessionRow({ session, account, onResume, busy, disabled }: { session: Session; account?: Account; onResume: (session: Session) => void; busy: boolean; disabled: boolean }) {
  return (
    <li className="session-row">
      <div className="session-icon"><TerminalIcon /></div>
      <div className="session-info">
        <strong>{session.title || 'Untitled session'}</strong>
        <span>{account?.id || session.provider}</span>
      </div>
      <span className="session-time"><ClockIcon /> {relativeTime(session.updatedAt)}</span>
      <button className="resume-button" disabled={disabled} onClick={() => onResume(session)}>{busy ? 'Preparing…' : 'Resume'} <ArrowIcon /></button>
    </li>
  )
}

export default function App() {
  const [state, setState] = useState<AgentHopState | null>(null)
  const [providerId, setProviderId] = useState('')
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [busyKey, setBusyKey] = useState('')
  const [modal, setModal] = useState<ModalState>(null)
  const stateRequest = useRef(0)

  const applyState = useCallback((next: AgentHopState, requestId: number) => {
    if (requestId !== stateRequest.current) return
    setState(next)
    setProviderId((current) => next.providers.some((item) => item.id === current) ? current : next.providers[0]?.id ?? '')
  }, [])

  const load = useCallback(async () => {
    const requestId = ++stateRequest.current
    setError('')
    try {
      const next = await api.getState()
      applyState(next, requestId)
    } catch (reason) {
      if (requestId === stateRequest.current) setError(reason instanceof Error ? reason.message : 'Could not connect to AgentHop.')
    }
  }, [applyState])

  useEffect(() => { void load() }, [load])

  const accounts = useMemo(() => state?.accounts.filter((account) => account.provider === providerId) ?? [], [state, providerId])
  const sessions = useMemo(() => state?.sessions.filter((session) => session.provider === providerId).slice(0, 6) ?? [], [state, providerId])
  const recommendedId = state?.recommendation?.provider === providerId ? state.recommendation.account : undefined
  const provider = state?.providers.find((item) => item.id === providerId)
  const commandAccount = useMemo(() => {
    const usable = (account: Account) => account.provider === providerId
      && account.authenticated
      && !account.duplicate
      && account.usage?.allowed !== false
      && account.usage?.status !== 'blocked'
    return state?.accounts.find((account) => usable(account) && account.active)
      ?? state?.accounts.find((account) => usable(account) && account.id === recommendedId)
      ?? state?.accounts.find(usable)
  }, [providerId, recommendedId, state])

  async function refresh() {
    const requestId = ++stateRequest.current
    setRefreshing(true)
    setError('')
    try {
      const next = await api.refresh()
      applyState(next, requestId)
    } catch (reason) {
      if (requestId === stateRequest.current) setError(reason instanceof Error ? reason.message : 'Refresh failed.')
    } finally {
      setRefreshing(false)
    }
  }

  async function activate(account: Account) {
    const key = `account:${account.provider}:${account.id}`
    ++stateRequest.current
    setBusyKey(key)
    setError('')
    try {
      await api.activate(account.provider, account.id)
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not switch accounts.')
    } finally {
      setBusyKey((current) => current === key ? '' : current)
    }
  }

  async function getCommand(account: Pick<Account, 'provider' | 'id'>, mode: CommandMode, sessionId?: string, sessionTitle?: string) {
    const key = sessionId ? `session:${account.provider}:${sessionId}` : `command:${account.provider}:${account.id}`
    setBusyKey(key)
    setError('')
    try {
      const result = await api.command(account.provider, account.id, mode, sessionId)
      setModal({ command: result.command, title: mode === 'resume' ? `Resume ${sessionTitle ?? 'session'}` : `New session with ${account.id}` })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create the command.')
    } finally {
      setBusyKey((current) => current === key ? '' : current)
    }
  }

  function resume(session: Session) {
    const account = session.provider === providerId ? commandAccount : undefined
    if (!account) {
      setError('Connect an account for this provider before resuming the session.')
      return
    }
    void getCommand(account, 'resume', session.id, session.title ?? undefined)
  }

  if (!state && !error) return <LoadingView />

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AgentHop home">
          <span className="brand-mark"><span /><span /></span>
          <span>Agent<span>Hop</span></span>
        </a>
        <div className="topbar-actions">
          {state && state.providers.length > 0 && (
            <label className="provider-select">
              <span className="sr-only">Provider</span>
              <span className={`provider-dot ${provider && (!provider.available || provider.error) ? 'provider-dot--warning' : ''}`} />
              <select value={providerId} onChange={(event) => setProviderId(event.target.value)}>
                {state.providers.map((item) => <option value={item.id} key={item.id}>{item.name}{!item.available ? ' (unavailable)' : ''}</option>)}
              </select>
            </label>
          )}
          <button className="icon-button refresh-button" onClick={() => void refresh()} disabled={refreshing || Boolean(busyKey)} aria-label="Refresh usage data">
            <RefreshIcon className={refreshing ? 'spin' : ''} />
          </button>
        </div>
      </header>

      <main className="main" id="top">
        {error && (
          <div className="error-banner" role="alert">
            <span><strong>Something went sideways.</strong> {error}</span>
            <button onClick={() => void load()}>Try again</button>
          </div>
        )}

        {!state ? (
          <section className="empty-state">
            <div className="empty-icon">!</div><h1>AgentHop is out of reach</h1><p>Check that the local service is running, then try again.</p>
            <button className="button button--primary" onClick={() => void load()}>Reconnect</button>
          </section>
        ) : state.providers.length === 0 ? (
          <section className="empty-state">
            <div className="empty-icon"><SparkIcon /></div><h1>Add your first provider</h1><p>Once an adapter is configured, its accounts and usage will appear here.</p>
          </section>
        ) : (
          <>
            <section className="hero">
              <div>
                <p className="eyebrow"><span /> Account control center</p>
                <h1>Pick up where you left off.</h1>
                <p>Move between accounts without losing the thread. AgentHop keeps your sessions close and your limits visible.</p>
              </div>
              <div className="hero-orbit" aria-hidden="true"><span>AH</span><i /><i /><i /></div>
            </section>

            <section aria-labelledby="accounts-heading">
              <div className="section-heading">
                <div><p className="section-kicker">{provider?.name ?? 'Provider'}</p><h2 id="accounts-heading">Your accounts</h2></div>
                {state.recommendation?.reason && recommendedId && <p className="recommendation-note"><SparkIcon /> {state.recommendation.reason}</p>}
              </div>
              {provider && (!provider.available || provider.error) && <div className="provider-warning" role="status">{provider.error || `${provider.name} is currently unavailable.`}</div>}
              {accounts.length > 0 ? (
                <div className="account-grid">
                  {accounts.map((account) => (
                    <AccountCard key={account.id} account={account} recommended={account.id === recommendedId} busy={busyKey === `account:${account.provider}:${account.id}` || busyKey === `command:${account.provider}:${account.id}`} disabled={Boolean(busyKey) || refreshing} onActivate={(item) => void activate(item)} onNewSession={(item) => void getCommand(item, 'new')} />
                  ))}
                </div>
              ) : <div className="inline-empty">No accounts are connected to this provider yet.</div>}
            </section>

            <section className="sessions-section" aria-labelledby="sessions-heading">
              <div className="section-heading"><div><p className="section-kicker">Continue working</p><h2 id="sessions-heading">Recent sessions</h2></div></div>
              {sessions.length > 0 ? (
                <ul className="session-list">
                  {sessions.map((session) => <SessionRow key={session.id} session={session} account={commandAccount} onResume={resume} busy={busyKey === `session:${session.provider}:${session.id}`} disabled={Boolean(busyKey) || refreshing || !commandAccount} />)}
                </ul>
              ) : <div className="inline-empty"><TerminalIcon /> No recent sessions. Start a new one from your active account.</div>}
            </section>
          </>
        )}
      </main>

      <footer><span>AgentHop</span><span>Local-first · Provider-neutral</span></footer>
      {modal && <CommandModal {...modal} onClose={() => setModal(null)} />}
    </div>
  )
}
