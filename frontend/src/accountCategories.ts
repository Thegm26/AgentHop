import type { Account, AccountStatus } from './types'

export interface AccountCategory {
  id: string
  label: string
  accounts: Account[]
  summary: string
}

function humanize(value: string) {
  return value
    .trim()
    .split(/[._\-\s]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(' ')
}

function categoryFor(account: Account) {
  const plan = account.usage?.plan?.trim()
  if (plan && plan.toLowerCase() !== 'free') {
    const label = humanize(plan)
    return { id: `plan:${label.toLowerCase()}`, label }
  }
  return { id: `profile:${account.id}`, label: humanize(account.id) || account.id }
}

function statusFor(account: Account): AccountStatus | 'disconnected' | 'duplicate' {
  if (account.duplicate) return 'duplicate'
  if (!account.authenticated) return 'disconnected'
  return account.usage?.status ?? 'unknown'
}

function summaryFor(accounts: Account[]) {
  const statuses = new Map<string, number>()
  for (const account of accounts) {
    const status = statusFor(account)
    statuses.set(status, (statuses.get(status) ?? 0) + 1)
  }
  const count = `${accounts.length} account${accounts.length === 1 ? '' : 's'}`
  const statusSummary = [...statuses]
    .map(([status, amount]) => `${amount} ${status}`)
    .join(' · ')
  return `${count} · ${statusSummary}`
}

export function accountCategories(accounts: Account[]): AccountCategory[] {
  const categories = new Map<string, { label: string; accounts: Account[] }>()
  for (const account of accounts) {
    const category = categoryFor(account)
    const current = categories.get(category.id)
    if (current) current.accounts.push(account)
    else categories.set(category.id, { label: category.label, accounts: [account] })
  }
  return [...categories.entries()].map(([id, category]) => ({
    id,
    label: category.label,
    accounts: category.accounts,
    summary: summaryFor(category.accounts),
  }))
}
