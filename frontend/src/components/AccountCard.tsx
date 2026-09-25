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
  onDelete: (account: Account) => void
  onRedeemResetCredit: (account: Account) => void
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

function localResetTime(value: number | null | undefined) {
  if (value == null) return null
  const date = fromEpoch(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function AccountCard({ account, recommended, busy, disabled, onActivate, onNewSession, onDelete, onRedeemResetCredit }: Props) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  const windows = [
    { label: '5-hour limit', usedPercent: account.usage?.fiveHourUsed, resetsAt: account.usage?.fiveHourResetsAt },
    { label: 'Weekly limit', usedPercent: account.usage?.weeklyUsed, resetsAt: account.usage?.weeklyResetsAt },
  ].filter((item): item is { label: string; usedPercent: number; resetsAt: number | null | undefined } => typeof item.usedPercent === 'number')
  const unavailable = !account.authenticated || account.duplicate || account.usage?.status === 'blocked' || account.usage?.status === 'error'
  const removable = account.id === 'default' || (!account.active && unavailable)
  const status = account.duplicate ? 'duplicate' : !account.authenticated ? 'disconnected' : account.usage?.status ?? 'unknown'
  const unblockAt = status === 'blocked' ? expectedUnblockAt(account) : null
  const unblockWait = unblockAt == null ? null : timeUntil(unblockAt, now)
  const email = account.email || (!account.authenticated || account.duplicate ? 'No email connected' : 'Email unavailable')

  return (
    <article className={`account-card ${account.active ? 'is-active' : ''} status-${status ?? 'unknown'}`}>
      <div className="account-card__top">
        <div className="avatar" aria-hidden="true">{account.id.slice(0, 2).toUpperCase()}</div>
        <div className="account-identity">
          <div className="account-name-row">
            <h3>{account.id}</h3>
            {account.active && <span className="pill pill--active"><span /> Active</span>}
            {recommended && <span className="pill pill--recommended"><SparkIcon /> Suggested profile</span>}
          </div>
          <p>{email}</p>
          <p>{account.usage?.plan || (account.authenticated ? 'Connected account' : 'Authentication required')}</p>
        </div>
        <div className={`account-state account-state--${status}`} aria-label={`Account state: ${status}`}>
          <strong>{status}</strong>
        </div>
      </div>

      <div className="usage-list" aria-label="Usage and reset details">
        <div className="usage-list__heading">
          <strong>Usage &amp; resets</strong>
          <span>Reported by Codex</span>
        </div>
        {windows.length === 0 ? (
          <div className="usage-empty">{account.usage?.error || 'Usage data hasn’t arrived yet.'}</div>
        ) : windows.map((window) => {
          const percentage = Math.min(100, Math.max(0, window.usedPercent))
          const remaining = Math.round(100 - percentage)
          const resetWait = timeUntil(window.resetsAt, now)
          const resetAt = localResetTime(window.resetsAt)
          return (
            <div className="usage-item" key={window.label}>
              <div className="usage-item__labels"><strong>{window.label}</strong></div>
              <div className="capacity-bar" role="progressbar" aria-label={`${window.label} remaining capacity`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={remaining}>
                <span style={{ width: `${remaining}%` }} />
              </div>
              <dl className="usage-details" aria-label={`${window.label} remaining capacity and reset details`}>
                <div><dt>Remaining</dt><dd>{remaining}%</dd></div>
                <div className="usage-details__reset"><dt><ClockIcon /> Reset</dt><dd>{resetAt ? <><time dateTime={fromEpoch(window.resetsAt!).toISOString()}>{resetAt}</time>{resetWait && ` (${resetWait})`}</> : 'Unavailable'}</dd></div>
              </dl>
            </div>
          )
        })}
      </div>

      {status === 'blocked' && <p className="account-unblock"><ClockIcon /> {unblockWait == null ? 'Unblock time unavailable' : unblockWait === 'now' ? 'Reset due; refresh status' : `Expected unblock ${unblockWait}`}</p>}

      <div className="account-actions">
        {(account.usage?.resetCreditsAvailable ?? 0) > 0 && <button className="button button--secondary" disabled={disabled} onClick={() => onRedeemResetCredit(account)}>{busy ? 'Redeeming…' : `Redeem usage limit reset (${account.usage?.resetCreditsAvailable})`}</button>}
        {account.duplicate && <span className="account-warning">Duplicate credentials</span>}
        {account.active ? (
          <button className="button button--primary" disabled={unavailable || disabled} onClick={() => onNewSession(account)}>{busy ? 'Preparing…' : unavailable ? 'Account unavailable' : 'Start new session'} <ArrowIcon /></button>
        ) : (
          <button className="button button--secondary" disabled={disabled || unavailable} onClick={() => onActivate(account)}>
            {busy ? 'Switching…' : unavailable ? 'Account unavailable' : 'Switch to account'} <ArrowIcon />
          </button>
        )}
        {removable && <button className="button button--danger" disabled={disabled} onClick={() => onDelete(account)}>{busy ? 'Removing…' : 'Delete profile'}</button>}
      </div>
    </article>
  )
}
