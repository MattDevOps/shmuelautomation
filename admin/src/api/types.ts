export const PROPERTY_TYPES = ['rent', 'sale'] as const
export type PropertyType = (typeof PROPERTY_TYPES)[number]

export const PROPERTY_STATUSES = ['available', 'rented', 'sold'] as const
export type PropertyStatus = (typeof PROPERTY_STATUSES)[number]

export const BROKER_FEE_STATUSES = ['yes', 'no', 'partial'] as const
export type BrokerFeeStatus = (typeof BROKER_FEE_STATUSES)[number]

export interface Property {
  id: string
  type: PropertyType
  status: PropertyStatus
  price: string
  currency: string
  rooms: string | null
  size_sqm: number | null
  floor: number | null
  address: string | null
  neighborhood: string | null
  city: string
  owner_name: string | null
  owner_phone: string | null
  broker_fee_status: BrokerFeeStatus
  broker_fee_amount: string | null
  description: string | null
  notes: string | null
  yad2_url: string | null
  created_at: string
  updated_at: string
}

export type PropertyCreate = Omit<Property, 'id' | 'created_at' | 'updated_at'>

export type PropertyUpdate = Partial<PropertyCreate>

export interface PropertyListFilters {
  type?: PropertyType
  status?: PropertyStatus
  neighborhood?: string
  min_price?: string
  max_price?: string
  q?: string
  limit?: number
  offset?: number
}

export interface Contact {
  id: string
  name: string
  phone: string | null
  email: string | null
  language: string | null
  segments: string[]
  notes: string | null
  source: string | null
  created_at: string
  updated_at: string
}

export type ContactCreate = Omit<Contact, 'id' | 'created_at' | 'updated_at'>

export type ContactUpdate = Partial<ContactCreate>

export const EMPTY_CONTACT: ContactCreate = {
  name: '',
  phone: null,
  email: null,
  language: null,
  segments: [],
  notes: null,
  source: 'manual',
}

export interface ContactListFilters {
  segment?: string[]
  q?: string
  limit?: number
  offset?: number
}

export const POST_SLOT_STATUSES = [
  'pending',
  'posted',
  'skipped',
  'cancelled',
] as const
export type PostSlotStatus = (typeof POST_SLOT_STATUSES)[number]

export interface PostSlotWithProperty {
  id: string
  property_id: string
  scheduled_for: string
  status: PostSlotStatus
  priority: number
  posted_at: string | null
  created_at: string
  property_type: PropertyType
  property_neighborhood: string | null
  property_address: string | null
  property_price: string
}

export interface PostCompose {
  text_en: string
  text_he: string
  whatsapp_share_url: string
  facebook_share_url: string | null
}

export interface CloudConnectionStatus {
  provider: string
  connected: boolean
  account_email: string | null
  root_folder_name: string | null
}

export interface CloudPhoto {
  id: string
  property_id: string
  provider: string
  external_id: string
  folder_external_id: string
  file_name: string
  mime_type: string
  size_bytes: number
  web_view_url: string | null
  thumbnail_url: string | null
  created_at: string
}

export interface Yad2ImportPreview {
  url: string
  title: string | null
  description: string | null
  price: string | null
  rooms: string | null
  size_sqm: number | null
  floor: number | null
  address: string | null
  neighborhood: string | null
  image_urls: string[]
  warnings: string[]
}

export const EMPTY_PROPERTY: PropertyCreate = {
  type: 'rent',
  status: 'available',
  price: '',
  currency: 'ILS',
  rooms: null,
  size_sqm: null,
  floor: null,
  address: null,
  neighborhood: null,
  city: 'Jerusalem',
  owner_name: null,
  owner_phone: null,
  broker_fee_status: 'yes',
  broker_fee_amount: null,
  description: null,
  notes: null,
  yad2_url: null,
}
