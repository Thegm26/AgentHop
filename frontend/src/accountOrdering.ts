import type { Account } from './types'

export function fromEpoch(value: number) {
  return new Date(value < 1_000_000_000_000 ? value * 1000 : value)
}

/**
 * The account cannot be used again until every exhausted usage window resets.
 */
export function expectedUnblockAt(account: Account) {
  const usage = account.usage
  if (!usage) return null

  const exhausted = [
    { used: usage.fiveHourUsed, resetsAt: usage.fiveHourResetsAt },
    { used: usage.weeklyUsed, resetsAt: usage.weeklyResetsAt },
  ].filter((window) => typeof window.used === 'number' && window.used >= 100)

  if (exhausted.length === 0 || exhausted.some((window) => window.resetsAt == null || !Number.isFinite(window.resetsAt))) return null
  const resetTimes = exhausted.map((window) => fromEpoch(window.resetsAt!).getTime())
  return resetTimes.every(Number.isFinite) ? Math.max(...resetTimes) : null
}

function isError(account: Account) {
  return account.usage?.status === 'error'
}

function isBlocked(account: Account) {
  return account.usage?.status === 'blocked'
}

function orderGroup(account: Account) {
  if (!account.authenticated || account.duplicate || isError(account)) return 3
  if (isBlocked(account)) return expectedUnblockAt(account) == null ? 2 : 1
  if (account.usage?.allowed === false) return 2
  return 0
}

/** Returns a sorted copy; API state and source account order remain untouched. */
export function sortAccountsByUsability(accounts: readonly Account[], recommendedId?: string) {
  return accounts
    .map((account, index) => ({ account, index, group: orderGroup(account), unblockAt: expectedUnblockAt(account) }))
    .sort((left, right) => {
      if (left.group !== right.group) return left.group - right.group
      if (left.group === 0) {
        const leftRecommended = left.account.id === recommendedId
        const rightRecommended = right.account.id === recommendedId
        if (leftRecommended !== rightRecommended) return leftRecommended ? -1 : 1
      }
      if (left.group === 1 && left.unblockAt !== right.unblockAt) return left.unblockAt! - right.unblockAt!
      return left.index - right.index
    })
    .map(({ account }) => account)
}
