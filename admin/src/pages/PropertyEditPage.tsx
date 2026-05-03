import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createProperty,
  getProperty,
  updateProperty,
} from '../api/properties'
import { EMPTY_PROPERTY, type PropertyCreate } from '../api/types'
import PhotoSection from '../components/PhotoSection'
import PropertyForm from '../components/PropertyForm'

export default function PropertyEditPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isCreate = id === undefined

  const [initial, setInitial] = useState<PropertyCreate | null>(
    isCreate ? EMPTY_PROPERTY : null,
  )
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (isCreate) return
    getProperty(id)
      .then((p) => {
        setInitial({
          type: p.type,
          status: p.status,
          price: p.price,
          currency: p.currency,
          rooms: p.rooms,
          size_sqm: p.size_sqm,
          floor: p.floor,
          address: p.address,
          neighborhood: p.neighborhood,
          city: p.city,
          owner_name: p.owner_name,
          owner_phone: p.owner_phone,
          broker_fee_status: p.broker_fee_status,
          broker_fee_amount: p.broker_fee_amount,
          description: p.description,
          notes: p.notes,
          yad2_url: p.yad2_url,
        })
      })
      .catch((e: Error) => setLoadError(e.message))
  }, [id, isCreate])

  async function save(payload: PropertyCreate): Promise<void> {
    if (isCreate) {
      await createProperty(payload)
    } else {
      await updateProperty(id, payload)
    }
    navigate('/')
  }

  if (loadError) {
    return (
      <p role="alert" className="error">
        Could not load property: {loadError}
      </p>
    )
  }
  if (initial === null) return <p>Loading…</p>

  const subhead = isCreate
    ? 'A new listing for the catalog. Fill in the price first; the rest can come later.'
    : initial.neighborhood
      ? `${initial.neighborhood} — ${initial.type === 'rent' ? 'for rent' : 'for sale'}`
      : `${initial.type === 'rent' ? 'For rent' : 'For sale'}`

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>{isCreate ? 'New property' : 'Edit property'}</h1>
          <p className="page-subhead" dir="auto">
            {subhead}
          </p>
        </div>
      </header>
      <PropertyForm
        initial={initial}
        submitLabel={isCreate ? 'Create' : 'Save changes'}
        onSubmit={save}
        onCancel={() => navigate('/')}
      />
      {!isCreate && id && <PhotoSection propertyId={id} />}
    </section>
  )
}
