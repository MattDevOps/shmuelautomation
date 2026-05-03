import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createContact, getContact, updateContact } from '../api/contacts'
import { EMPTY_CONTACT, type ContactCreate } from '../api/types'
import ContactForm from '../components/ContactForm'

export default function ContactEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isCreate = id === undefined

  const [initial, setInitial] = useState<ContactCreate | null>(
    isCreate ? EMPTY_CONTACT : null,
  )
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (isCreate) return
    getContact(id)
      .then((c) => {
        setInitial({
          name: c.name,
          phone: c.phone,
          email: c.email,
          language: c.language,
          segments: c.segments,
          notes: c.notes,
          source: c.source,
        })
      })
      .catch((e: Error) => setLoadError(e.message))
  }, [id, isCreate])

  async function save(payload: ContactCreate): Promise<void> {
    if (isCreate) {
      await createContact(payload)
    } else {
      await updateContact(id, payload)
    }
    navigate('/contacts')
  }

  if (loadError) {
    return (
      <p role="alert" className="error">
        Could not load contact: {loadError}
      </p>
    )
  }
  if (initial === null) return <p className="muted">Loading…</p>

  const subhead = isCreate
    ? 'Add a person to the address book — phone is optional but helps for WhatsApp.'
    : `Editing ${initial.name}`

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>{isCreate ? 'New contact' : 'Edit contact'}</h1>
          <p className="page-subhead" dir="auto">
            {subhead}
          </p>
        </div>
      </header>
      <ContactForm
        initial={initial}
        submitLabel={isCreate ? 'Create' : 'Save changes'}
        onSubmit={save}
        onCancel={() => navigate('/contacts')}
      />
    </section>
  )
}
