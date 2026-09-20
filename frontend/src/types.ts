export interface Provider {
  id: string
  name: string
  available: boolean
  error?: string | null
}

export type AccountStatus = 'ready' | 'close' | 'critical' | 'blocked' | 'error' | 'unknown'

export interface AccountUsage {
  plan?: string | null
  fiveHourUsed?: number | null
  fiveHourResetsAt?: number | null
  weeklyUsed?: number | null
  weeklyResetsAt?: number | null
  allowed?: boolean | null
  status: AccountStatus
  error?: string | null
}

export interface Account {
  provider: string
  id: string
  active: boolean
  authenticated: boolean
  duplicate: boolean
  email?: string | null
  usage?: AccountUsage | null
}

export interface Session {
  provider: string
  id: string
  title?: string | null
  updatedAt?: number | null
}

export interface Recommendation {
  provider: string
  account: string
  reason: string
}

export interface AgentHopState {
  providers: Provider[]
  accounts: Account[]
  sessions: Session[]
  recommendation: Recommendation | null
}

export type CommandMode = 'new' | 'resume'
