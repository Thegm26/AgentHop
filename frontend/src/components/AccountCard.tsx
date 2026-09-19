import { ArrowIcon, ClockIcon, SparkIcon } from './Icons'
import type { Account } from '../types'

interface Props {
  account: Account
  recommended: boolean
  busy: boolean
  disabled: boolean
  onActivate: (account: Account) => void
  onNewSession: (account: Account) => void
}

function fromEpoch(value: number) {
  return new Date(value < 1_000_000_000_000 ? value * 1000 : value)
}

function resetLabel(value?: number | null) {
  if (value == null) return 'Reset time unavailable'
  const date = fromEpoch(value)
  if (Number.isNaN(date.getTime())) return 'Reset time unavailable'
  return `Resets ${new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' }).format(date)}`
}

export function AccountCard({ account, recommended, busy, disabled, onActivate, onNewSession }: Props) {
  const windows = [
    { label: '5-hour limit', usedPercent: account.usage?.fiveHourUsed, resetsAt: account.usage?.fiveHourResetsAt },
    { label: 'Weekly limit', usedPercent: account.usage?.weeklyUsed, resetsAt: account.usage?.weeklyResetsAt },
  ].filter((item): item is { label: string; usedPercent: number; resetsAt: number | null | undefined } => typeof item.usedPercent === 'number')
  const knownUsed = account.usage?.fiveHourUsed ?? account.usage?.weeklyUsed
  const used = Math.min(100, Math.max(0, knownUsed ?? 0))
  const remaining = 100 - used
  const unavailable = !account.authenticated || account.duplicate || account.usage?.allowed === false || account.usage?.status === 'blocked'
  const status = account.usage?.status

  return (
    <article className={`account-card ${account.active ? 'is-active' : ''} status-${status ?? 'unknown'}`}>
      <div className="account-card__top">
        <div className="avatar" aria-hidden="true">{account.id.slice(0, 2).toUpperCase()}</div>
        <div className="account-identity">
          <div className="account-name-row">
            <h3>{account.id}</h3>
            {account.active && <span className="pill pill--active"><span /> Active</span>}
            {recommended && <span className="pill pill--recommended"><SparkIcon /> Best choice</span>}
            {status && !['ready', 'unknown'].includes(status) && <span className={`pill pill--${status}`}>{status}</span>}
          </div>
          <p>{account.usage?.plan || (account.authenticated ? 'Connected account' : 'Authentication required')}</p>
        </div>
        <div className={`usage-ring ${knownUsed == null ? 'usage-ring--unknown' : ''}`} style={{ '--usage': `${remaining * 3.6}deg` } as React.CSSProperties} role="img" aria-label={knownUsed == null ? 'Usage unavailable' : `${Math.round(remaining)} percent remaining`}>
          <div><strong>{knownUsed == null ? '—' : `${Math.round(remaining)}%`}</strong><span>{knownUsed == null ? 'usage' : 'left'}</span></div>
        </div>
      </div>

      <div className="usage-list">
        {windows.length === 0 ? (
          <div className="usage-empty">{account.usage?.error || 'Usage data hasn’t arrived yet.'}</div>
        ) : windows.map((window) => {
          const percentage = Math.min(100, Math.max(0, window.usedPercent))
          return (
            <div className="usage-item" key={window.label}>
              <div className="usage-item__labels"><span>{window.label}</span><strong>{Math.round(100 - percentage)}% left</strong></div>
              <div className="progress" role="progressbar" aria-label={`${window.label} usage`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage}>
                <span style={{ width: `${percentage}%` }} />
              </div>
              <span className="reset"><ClockIcon /> {resetLabel(window.resetsAt)}</span>
            </div>
          )
        })}
      </div>

      <div className="account-actions">
        {account.duplicate && <span className="account-warning">Duplicate credentials</span>}
        {account.active ? (
          <button className="button button--primary" disabled={unavailable || disabled} onClick={() => onNewSession(account)}>{busy ? 'Preparing…' : unavailable ? 'Account unavailable' : 'Start new session'} <ArrowIcon /></button>
        ) : (
          <button className="button button--secondary" disabled={disabled || unavailable} onClick={() => onActivate(account)}>
            {busy ? 'Switching…' : unavailable ? 'Account unavailable' : 'Switch to account'} <ArrowIcon />
          </button>
        )}
      </div>
    </article>
  )
}
