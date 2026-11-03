import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AccountCard } from './AccountCard'
import type { Account } from '../types'

const account: Account = {
  provider: 'codex', id: 'work', active: true, authenticated: true, duplicate: false,
  usage: { status: 'ready', resetCreditsAvailable: 2 },
}

function renderAccount(value: Account) {
  const onRedeemResetCredit = vi.fn()
  render(<AccountCard account={value} recommended={false} busy={false} disabled={false}
    onActivate={vi.fn()} onDelete={vi.fn()} onReconnect={vi.fn()} onRefresh={vi.fn()}
    onRedeemResetCredit={onRedeemResetCredit} />)
  return onRedeemResetCredit
}

describe('AccountCard usage reset credits', () => {
  afterEach(cleanup)

  it.each(['ready', 'blocked'] as const)('shows a positive count and keeps redemption manual for %s accounts', (status) => {
    const value = { ...account, usage: { ...account.usage!, status } }
    const redeem = renderAccount(value)
    expect(within(screen.getByLabelText('Usage resets left')).getByRole('definition')).toHaveTextContent('2')
    expect(screen.getByRole('button', { name: 'Redeem usage limit reset (2)' })).toBeEnabled()
    expect(redeem).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Redeem usage limit reset (2)' }))
    expect(redeem).toHaveBeenCalledExactlyOnceWith(value)
  })

  it.each([0, undefined, null, -1, 1.5, NaN, '2', true])('shows Unavailable for count %s', (credits) => {
    renderAccount({ ...account, usage: { status: 'ready', resetCreditsAvailable: credits } } as unknown as Account)
    expect(within(screen.getByLabelText('Usage resets left')).getByRole('definition')).toHaveTextContent('Unavailable')
    expect(screen.queryByRole('button', { name: /Redeem usage limit reset/ })).not.toBeInTheDocument()
  })

  it.each([
    { ...account, usage: null },
    { ...account, usage: { ...account.usage!, status: 'error' as const, error: 'Timed out' } },
    { ...account, usage: { ...account.usage!, error: 'Failed probe' } },
    { ...account, authenticated: false },
    { ...account, duplicate: true },
  ])('does not present stale credits as available', (value) => {
    renderAccount(value)
    expect(within(screen.getByLabelText('Usage resets left')).getByRole('definition')).toHaveTextContent('Unavailable')
    expect(screen.queryByRole('button', { name: /Redeem usage limit reset/ })).not.toBeInTheDocument()
  })
})
