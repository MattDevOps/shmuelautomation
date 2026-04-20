import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import App from './App'

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders heading and pending status before fetch resolves', () => {
    vi.spyOn(global, 'fetch').mockImplementation(() => new Promise(() => {}))
    render(<App />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/admin/i)
    expect(screen.getByTestId('health-status')).toHaveTextContent('unknown')
  })

  it('shows ok when backend responds healthy', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    )
    render(<App />)
    expect(await screen.findByText('ok')).toBeInTheDocument()
  })

  it('shows unreachable when backend fails', async () => {
    vi.spyOn(global, 'fetch').mockRejectedValue(new Error('network'))
    render(<App />)
    expect(await screen.findByText('unreachable')).toBeInTheDocument()
  })
})
