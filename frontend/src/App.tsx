import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { AccountCard } from './components/AccountCard'
import { CommandModal } from './components/CommandModal'
import { RefreshIcon, SparkIcon } from './components/Icons'
import type { Account, AgentHopState } from './types'

type ModalState = { command: string; title: string } | null

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
      const next = await api.refresh()
      applyState(next, requestId)
    } catch (reason) {
      if (requestId === stateRequest.current) setError(reason instanceof Error ? reason.message : 'Could not connect to AgentHop.')
    }
  }, [applyState])

  useEffect(() => { void load() }, [load])

  const accounts = useMemo(() => state?.accounts.filter((account) => account.provider === providerId) ?? [], [state, providerId])
  const recommendedId = state?.recommendation?.provider === providerId ? state.recommendation.account : undefined
  const provider = state?.providers.find((item) => item.id === providerId)

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

  async function getCommand(account: Pick<Account, 'provider' | 'id'>) {
    const key = `command:${account.provider}:${account.id}`
    setBusyKey(key)
    setError('')
    try {
      const result = await api.command(account.provider, account.id, 'new')
      setModal({ command: result.command, title: `New session with ${account.id}` })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create the command.')
    } finally {
      setBusyKey((current) => current === key ? '' : current)
    }
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
          <button className="refresh-button" onClick={() => void refresh()} disabled={refreshing || Boolean(busyKey)}>
            <RefreshIcon className={refreshing ? 'spin' : ''} aria-hidden="true" />
            <span>{refreshing ? 'Refreshing…' : 'Refresh usage'}</span>
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
                    <AccountCard key={account.id} account={account} recommended={account.id === recommendedId} busy={busyKey === `account:${account.provider}:${account.id}` || busyKey === `command:${account.provider}:${account.id}`} disabled={Boolean(busyKey) || refreshing} onActivate={(item) => void activate(item)} onNewSession={(item) => void getCommand(item)} />
                  ))}
                </div>
              ) : <div className="inline-empty">No accounts are connected to this provider yet.</div>}
            </section>

          </>
        )}
      </main>

      <footer><span>AgentHop</span><span>Local-first · Provider-neutral</span></footer>
      {modal && <CommandModal {...modal} onClose={() => setModal(null)} />}
    </div>
  )
}
