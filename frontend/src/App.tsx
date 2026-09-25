import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './api'
import { AccountCard } from './components/AccountCard'
import { CommandModal } from './components/CommandModal'
import { RefreshIcon, SparkIcon } from './components/Icons'
import type { Account, AgentHopState } from './types'
import { sortAccountsByUsability } from './accountOrdering'
import { accountCategories } from './accountCategories'

type ModalState = { command: string; title: string; description?: string } | null
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
  const [addingAccount, setAddingAccount] = useState(false)
  const [newAccount, setNewAccount] = useState('')
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)
  const stateRequest = useRef(0)
  const statePromise = useRef<Promise<void> | null>(null)
  const refreshPromise = useRef<Promise<void> | null>(null)
  const operationInProgress = useRef(false)

  const applyState = useCallback((next: AgentHopState, requestId: number) => {
    if (requestId !== stateRequest.current) return
    setState(next)
    setProviderId((current) => next.providers.some((item) => item.id === current) ? current : next.providers[0]?.id ?? '')
  }, [])

  const load = useCallback(() => {
    if (statePromise.current) return statePromise.current
    const requestId = ++stateRequest.current
    const request = (async () => {
      setError('')
      try {
        const next = await api.getState()
        applyState(next, requestId)
      } catch (reason) {
        if (requestId === stateRequest.current) setError(reason instanceof Error ? reason.message : 'Could not connect to AgentHop.')
      }
    })()
    statePromise.current = request
    void request.finally(() => {
      if (statePromise.current === request) statePromise.current = null
    })
    return request
  }, [applyState])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setSelectedCategoryId(null)
  }, [providerId])

  const recommendedId = state?.recommendation?.provider === providerId ? state.recommendation.account : undefined
  const accounts = useMemo(() => sortAccountsByUsability(state?.accounts.filter((account) => account.provider === providerId) ?? [], recommendedId), [state, providerId, recommendedId])
  const categories = useMemo(() => accountCategories(accounts), [accounts])
  const selectedCategory = categories.find((category) => category.id === selectedCategoryId)
  const displayedAccounts = selectedCategory ? selectedCategory.accounts : accounts
  const provider = state?.providers.find((item) => item.id === providerId)
  const canOnboard = providerId === 'codex' && Boolean(provider?.available) && !provider?.error
  useEffect(() => {
    if (selectedCategoryId && !selectedCategory) setSelectedCategoryId(null)
  }, [selectedCategory, selectedCategoryId])

  const refresh = useCallback(async () => {
    if (operationInProgress.current) return
    if (refreshPromise.current) return refreshPromise.current
    const requestId = ++stateRequest.current
    const request = (async () => {
      setRefreshing(true)
      setError('')
      try {
        applyState(await api.refresh(), requestId)
      } catch (reason) {
        if (requestId === stateRequest.current) setError(reason instanceof Error ? reason.message : 'Could not connect to AgentHop.')
      } finally {
        setRefreshing(false)
      }
    })()
    refreshPromise.current = request
    void request.finally(() => {
      if (refreshPromise.current === request) refreshPromise.current = null
    })
    return request
  }, [applyState])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh()
    }, 3_600_000)
    return () => window.clearInterval(timer)
  }, [refresh])

  async function waitForStateRequests() {
    await Promise.all([statePromise.current, refreshPromise.current])
  }

  async function activate(account: Account) {
    if (operationInProgress.current) return
    const key = `account:${account.provider}:${account.id}`
    operationInProgress.current = true
    setBusyKey(key)
    setError('')
    try {
      await waitForStateRequests()
      await api.activate(account.provider, account.id)
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not switch accounts.')
    } finally {
      operationInProgress.current = false
      setBusyKey((current) => current === key ? '' : current)
    }
  }

  async function redeemResetCredit(account: Account) {
    if (operationInProgress.current) return
    const available = account.usage?.resetCreditsAvailable ?? 0
    if (!available || !window.confirm(`Redeem usage limit reset? You have ${available} usage limit reset${available === 1 ? '' : 's'} available.`)) return
    const key = `reset-credit:${account.provider}:${account.id}`
    operationInProgress.current = true
    setBusyKey(key)
    setError('')
    try {
      await waitForStateRequests()
      await api.redeemResetCredit(account.provider, account.id)
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not redeem the usage-limit reset.')
    } finally {
      operationInProgress.current = false
      setBusyKey((current) => current === key ? '' : current)
    }
  }

  async function onboard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const account = newAccount.trim()
    if (!providerId) return
    if (operationInProgress.current) return
    operationInProgress.current = true
    setBusyKey('onboard')
    setError('')
    let result: Awaited<ReturnType<typeof api.onboard>>
    try {
      await waitForStateRequests()
      result = await api.onboard(providerId, account)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add the account.')
      operationInProgress.current = false
      setBusyKey('')
      return
    }
    setAddingAccount(false)
    setNewAccount('')
    setModal({ command: result.command, title: `Connect ${result.account}`, description: 'Run this in your terminal and complete the Codex sign-in in your browser. Then return here and refresh usage and reset times.' })
    await load()
    operationInProgress.current = false
    setBusyKey('')
  }

  function cancelOnboarding() {
    setAddingAccount(false)
    setNewAccount('')
  }

  async function removeAccount(account: Account) {
    if (operationInProgress.current) return
    const prompt = account.id === 'default'
      ? 'Delete the default profile? Its Codex credentials and configuration will be removed; sessions and shared state will stay on disk.'
      : `Delete profile “${account.id}”? Its local Codex data will be permanently removed.`
    if (!window.confirm(prompt)) return
    operationInProgress.current = true
    setBusyKey('remove')
    setError('')
    try {
      await waitForStateRequests()
      await api.remove(account.provider, account.id)
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not remove the profile.')
    } finally {
      operationInProgress.current = false
      setBusyKey('')
    }
  }

  if (!state && !error) return <LoadingView />

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AgentHop home">
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
            <span>{refreshing ? 'Refreshing…' : 'Refresh usage & resets'}</span>
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
                <p>Move between profiles without losing the thread. AgentHop keeps your sessions close and your account status visible.</p>
              </div>
              <div className="hero-illustration">
                <img src="/assets/agenthop-mascot.png" width="1254" height="1254" alt="AgentHop mascot meditating while companion agents work around it" />
              </div>
            </section>

            <section aria-labelledby="accounts-heading">
              <div className="section-heading">
                <div><p className="section-kicker">{provider?.name ?? 'Provider'}</p><h2 id="accounts-heading">Your accounts</h2></div>
                <div className="section-actions">
                  {providerId === 'codex' && <button className="button button--secondary" onClick={() => setAddingAccount((current) => !current)} disabled={!canOnboard || Boolean(busyKey) || refreshing}>Add account</button>}
                </div>
              </div>
              {addingAccount && canOnboard && <form className="onboard-form" onSubmit={(event) => void onboard(event)}>
                <label htmlFor="new-account">New account name</label>
                <div className="onboard-controls"><input id="new-account" value={newAccount} onChange={(event) => setNewAccount(event.target.value)} placeholder="e.g. account-05 (optional)" pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,63}" maxLength={64} autoFocus /><button className="button button--primary" type="submit" disabled={Boolean(busyKey) || refreshing}>{busyKey === 'onboard' ? 'Preparing…' : 'Create profile'}</button><button className="button button--secondary" type="button" onClick={cancelOnboarding} disabled={Boolean(busyKey) || refreshing}>Cancel</button></div>
                <p>Creates a separate local profile. Leave the name blank to use the next available account number. You’ll run a terminal command to sign in; no password is entered here.</p>
              </form>}
              {provider && (!provider.available || provider.error) && <div className="provider-warning" role="status">{provider.error || `${provider.name} is currently unavailable.`}</div>}
              {categories.length > 1 && (
                <nav className="category-filters" aria-label="Account categories">
                  <button className="category-filter" type="button" aria-pressed={!selectedCategory} onClick={() => setSelectedCategoryId(null)}>All accounts</button>
                  {categories.map((category) => (
                    <button className="category-filter" type="button" key={category.id} aria-pressed={selectedCategoryId === category.id} onClick={() => setSelectedCategoryId(category.id)}>{category.label} <span>({category.accounts.length})</span></button>
                  ))}
                </nav>
              )}
              {displayedAccounts.length > 0 ? (
                <>
                <div className="account-grid">
                  {displayedAccounts.map((account) => (
                    <AccountCard key={account.id} account={account} recommended={account.id === recommendedId} busy={busyKey === `account:${account.provider}:${account.id}` || busyKey === `reset-credit:${account.provider}:${account.id}` || busyKey === 'remove'} disabled={Boolean(busyKey) || refreshing} onActivate={(item) => void activate(item)} onDelete={(item) => void removeAccount(item)} onRedeemResetCredit={(item) => void redeemResetCredit(item)} />
                  ))}
                </div>
                </>
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
