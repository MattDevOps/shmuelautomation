import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EMPTY_PROPERTY } from '../api/types'
import PropertyForm from './PropertyForm'

function setup() {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  const onCancel = vi.fn()
  render(
    <PropertyForm
      initial={EMPTY_PROPERTY}
      submitLabel="Create"
      onSubmit={onSubmit}
      onCancel={onCancel}
    />,
  )
  return { onSubmit, onCancel }
}

describe('PropertyForm', () => {
  it('does not call onSubmit when price is empty', async () => {
    const { onSubmit } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits a payload with non-empty fields converted from inputs', async () => {
    const { onSubmit } = setup()

    await userEvent.type(
      screen.getByRole('spinbutton', { name: /^price$/i }),
      '8500',
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: /^neighborhood$/i }),
      'Baka',
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: /^owner phone$/i }),
      '+972500000000',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0]![0]).toMatchObject({
      type: 'rent',
      status: 'available',
      currency: 'ILS',
      price: '8500',
      neighborhood: 'Baka',
      owner_phone: '+972500000000',
    })
  })

  it('coerces empty optional inputs to null in payload', async () => {
    const { onSubmit } = setup()
    await userEvent.type(
      screen.getByRole('spinbutton', { name: /^price$/i }),
      '8500',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    const payload = onSubmit.mock.calls[0]![0]
    expect(payload.neighborhood).toBeNull()
    expect(payload.owner_phone).toBeNull()
    expect(payload.description).toBeNull()
  })

  it('cancel button calls onCancel without submit', async () => {
    const { onCancel, onSubmit } = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows error message when onSubmit rejects', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('500 boom'))
    const onCancel = vi.fn()
    render(
      <PropertyForm
        initial={{ ...EMPTY_PROPERTY, price: '8500' }}
        submitLabel="Create"
        onSubmit={onSubmit}
        onCancel={onCancel}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/500 boom/)
  })
})
