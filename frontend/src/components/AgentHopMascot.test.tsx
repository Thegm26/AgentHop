import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AgentHopMascot } from './AgentHopMascot'

describe('AgentHopMascot', () => {
  it('renders the accessible hero illustration', () => {
    render(<AgentHopMascot aria-label="AgentHop courier" />)

    expect(screen.getByRole('img', { name: 'AgentHop courier' })).toHaveAttribute('viewBox', '0 0 220 180')
  })
})
