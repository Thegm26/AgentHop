import { describe, expect, it } from 'vitest'
import { expectedUnblockAt, sortAccountsByUsability } from './accountOrdering'
import type { Account } from './types'

function account(id: string, overrides: Partial<Account> = {}): Account {
  return { provider: 'codex', id, active: false, authenticated: true, duplicate: false, usage: { status: 'ready' }, ...overrides }
}

describe('account ordering', () => {
  it('uses the later exhausted reset and accepts epoch seconds or milliseconds', () => {
    const later = 2_000_000_000_000
    const blocked = account('both', { usage: { status: 'blocked', fiveHourUsed: 100, fiveHourResetsAt: 1_999_999_000, weeklyUsed: 100, weeklyResetsAt: later } })

    expect(expectedUnblockAt(blocked)).toBe(later)
  })

  it('places ready accounts before known blocked accounts, then orders blocked accounts by unblock time', () => {
    const accounts = [
      account('blocked-later', { usage: { status: 'blocked', fiveHourUsed: 100, fiveHourResetsAt: 2_000_000_300 } }),
      account('ready'),
      account('blocked-sooner', { usage: { status: 'blocked', weeklyUsed: 100, weeklyResetsAt: 2_000_000_100 } }),
    ]

    expect(sortAccountsByUsability(accounts).map(({ id }) => id)).toEqual(['ready', 'blocked-sooner', 'blocked-later'])
  })

  it('puts blocked accounts with an unknown reset after blocked accounts with a known reset', () => {
    const accounts = [
      account('unknown-reset', { usage: { status: 'blocked', fiveHourUsed: 100 } }),
      account('known-reset', { usage: { status: 'blocked', fiveHourUsed: 100, fiveHourResetsAt: 2_000_000_100 } }),
    ]

    expect(sortAccountsByUsability(accounts).map(({ id }) => id)).toEqual(['known-reset', 'unknown-reset'])
  })

  it('keeps equivalent accounts in source order while prioritizing the recommendation', () => {
    const accounts = [account('first'), account('recommended'), account('last')]
    const sorted = sortAccountsByUsability(accounts, 'recommended')

    expect(sorted.map(({ id }) => id)).toEqual(['recommended', 'first', 'last'])
    expect(accounts.map(({ id }) => id)).toEqual(['first', 'recommended', 'last'])
  })
})
