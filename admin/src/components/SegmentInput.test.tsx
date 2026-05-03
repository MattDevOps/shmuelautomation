import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SegmentInput from './SegmentInput'

describe('SegmentInput', () => {
  it('adds a segment when the user types and presses Enter', async () => {
    const onChange = vi.fn()
    render(<SegmentInput value={[]} onChange={onChange} />)

    await userEvent.type(screen.getByRole('combobox'), 'buyer{Enter}')
    expect(onChange).toHaveBeenCalledWith(['buyer'])
  })

  it('adds a segment when the user types a comma', async () => {
    const onChange = vi.fn()
    render(<SegmentInput value={[]} onChange={onChange} />)

    await userEvent.type(screen.getByRole('combobox'), 'buyer,')
    expect(onChange).toHaveBeenCalledWith(['buyer'])
  })

  it('removes a segment when the × button is clicked', async () => {
    const onChange = vi.fn()
    render(<SegmentInput value={['buyer', 'vip']} onChange={onChange} />)

    await userEvent.click(
      screen.getByRole('button', { name: /remove buyer/i }),
    )
    expect(onChange).toHaveBeenCalledWith(['vip'])
  })

  it('does not add duplicate segments', async () => {
    const onChange = vi.fn()
    render(<SegmentInput value={['buyer']} onChange={onChange} />)

    await userEvent.type(screen.getByRole('combobox'), 'buyer{Enter}')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('removes the last segment when Backspace is pressed in an empty input', async () => {
    const onChange = vi.fn()
    render(<SegmentInput value={['buyer', 'vip']} onChange={onChange} />)

    const input = screen.getByRole('combobox')
    input.focus()
    await userEvent.keyboard('{Backspace}')
    expect(onChange).toHaveBeenCalledWith(['buyer'])
  })

  it('exposes a datalist of suggestions when provided', () => {
    render(
      <SegmentInput
        value={[]}
        onChange={() => {}}
        suggestions={['buyer', 'renter']}
      />,
    )
    // datalist is in the DOM but not exposed via role; query directly
    const options = document.querySelectorAll('datalist option')
    expect(options.length).toBe(2)
  })
})
