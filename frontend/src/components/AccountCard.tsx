import { useEffect, useState } from 'react'
import { ArrowIcon, ClockIcon, SparkIcon } from './Icons'
import type { Account } from '../types'
import { expectedUnblockAt, fromEpoch } from '../accountOrdering'

interface Props {
  account: Account
  recommended: boolean
  busy: boolean
  disabled: boolean
  onActivate: (account: Account) => void
  onNewSession: (account: Account) => void
}

function timeUntil(value: number | null | undefined, now: number) {
  if (value == null) return null
  const date = fromEpoch(value)
  if (Number.isNaN(date.getTime())) return null
  const totalMinutes = Math.ceil((date.getTime() - now) / 60_000)
  if (totalMinutes <= 0) return 'now'
  const days = Math.floor(totalMinutes / 1_440)
  const hours = Math.floor((totalMinutes % 1_440) / 60)
  const minutes = totalMinutes % 60
  if (days > 0) return `in ${days}d ${hours}h`
  if (hours > 0) return `in ${hours}h ${minutes}m`
  return `in ${minutes}m`
}

export function AccountCard({ account, recommended, busy, disabled, onActivate, onNewSession }: Props) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const windows = [
    { label: '5-hour limit', usedPercent: account.usage?.fiveHourUsed, resetsAt: account.usage?.fiveHourResetsAt },
    { label: 'Weekly limit', usedPercent: account.usage?.weeklyUsed, resetsAt: account.usage?.weeklyResetsAt },
  ].filter((item): item is { label: string; usedPercent: number; resetsAt: number | null | undefined } => typeof item.usedPercent === 'number')
  const unavailable = !account.authenticated || account.duplicate || account.usage?.allowed === false || account.usage?.status === 'blocked'
  const status = account.duplicate ? 'duplicate' : !account.authenticated ? 'disconnected' : account.usage?.status ?? 'unknown'
  const unblockAt = status === 'blocked' ? expectedUnblockAt(account) : null
  const unblockWait = unblockAt == null ? null : timeUntil(unblockAt, now)

  return (
    <article className={`account-card ${account.active ? 'is-active' : ''} status-${status ?? 'unknown'}`}>
      <div className="account-card__top">
        <div className="avatar" aria-hidden="true">{account.id.slice(0, 2).toUpperCase()}</div>
        <div className="account-identity">
          <div className="account-name-row">
            <h3>{account.id}</h3>
            {account.active && <span className="pill pill--active"><span /> Active</span>}
            {recommended && <span className="pill pill--recommended"><SparkIcon /> Best choice</span>}
          </div>
          <p>{account.usage?.plan || (account.authenticated ? 'Connected account' : 'Authentication required')}</p>
        </div>
        <div className={`account-state account-state--${status}`} aria-label={`Account state: ${status}`}>
          <strong>{status}</strong>
        </div>
      </div>

      <div className="usage-list">
        {windows.length === 0 ? (
          <div className="usage-empty">{account.usage?.error || 'Usage data hasn’t arrived yet.'}</div>
        ) : windows.map((window) => {
          const percentage = Math.min(100, Math.max(0, window.usedPercent))
          const resetWait = timeUntil(window.resetsAt, now)
          return (
            <div className="usage-item" key={window.label}>
              <div className="usage-item__labels"><span>{window.label}</span><strong>{Math.round(100 - percentage)}% left</strong></div>
              <div className="progress" role="progressbar" aria-label={`${window.label} usage`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={percentage}>
                <span style={{ width: `${percentage}%` }} />
              </div>
              <span className="reset" title={window.resetsAt == null ? undefined : fromEpoch(window.resetsAt).toLocaleString()}><ClockIcon /> {resetWait ? `Resets ${resetWait}` : 'Reset time unavailable'}</span>
            </div>
          )
        })}
      </div>

      {status === 'blocked' && <p className="account-unblock"><ClockIcon /> {unblockWait == null ? 'Unblock time unavailable' : unblockWait === 'now' ? 'Reset due; refresh status' : `Expected unblock ${unblockWait}`}</p>}

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
