/**
 * Canonical Layer 1 records (DERIVED from `app/schemas/canonical/*.py` and the entity list routes).
 */

import { z } from 'zod';

import { decimalText, isoDate, isoDateTime, page, sha256Hex, uuid } from './common';

export const ENTITY_TYPES = [
  'organizations',
  'employees',
  'customers',
  'deals',
  'projects',
  'support_tickets',
  'documents',
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];

const base = {
  id: uuid,
  source_system: z.string(),
  source_entity: z.string(),
  source_id: z.string(),
  source_updated_at: isoDateTime.nullable(),
  ingested_at: isoDateTime,
  ingestion_run_id: uuid,
  record_hash: sha256Hex,
};

const text = z.string().nullable();

export const organization = z.strictObject({
  ...base,
  name: z.string(),
  industry: text,
  country: text,
  status: text,
});

export const employee = z.strictObject({
  ...base,
  name: z.string(),
  email: text,
  department: text,
  title: text,
  manager_source_id: text,
  status: text,
  hire_date: isoDate.nullable(),
  is_active: z.boolean(),
  organization_id: uuid.nullable(),
});

export const customer = z.strictObject({
  ...base,
  name: z.string(),
  email: text,
  segment: text,
  industry: text,
  status: text,
  owner_source_id: text,
  created_at: isoDateTime.nullable(),
  is_active: z.boolean(),
});

export const deal = z.strictObject({
  ...base,
  name: z.string(),
  stage: text,
  amount: decimalText.nullable(),
  currency: text,
  probability: decimalText.nullable(),
  expected_close_date: isoDate.nullable(),
  is_active: z.boolean(),
  customer_source_id: text,
  owner_source_id: text,
  customer_id: uuid.nullable(),
});

export const project = z.strictObject({
  ...base,
  name: z.string(),
  status: text,
  start_date: isoDate.nullable(),
  end_date: isoDate.nullable(),
  budget: decimalText.nullable(),
  is_active: z.boolean(),
  customer_source_id: text,
  owner_source_id: text,
  customer_id: uuid.nullable(),
});

export const supportTicket = z.strictObject({
  ...base,
  subject: text,
  description: text,
  priority: text,
  status: text,
  category: text,
  created_at: isoDateTime.nullable(),
  resolved_at: isoDateTime.nullable(),
  customer_source_id: text,
  assignee_source_id: text,
  customer_id: uuid.nullable(),
});

export const document = z.strictObject({
  ...base,
  title: text,
  document_type: text,
  body_text: text,
  source_uri: text,
  owner_source_id: text,
  created_at: isoDateTime.nullable(),
  updated_at: isoDateTime.nullable(),
});

export const entityRecords = {
  organizations: organization,
  employees: employee,
  customers: customer,
  deals: deal,
  projects: project,
  support_tickets: supportTicket,
  documents: document,
} as const satisfies Record<EntityType, z.ZodType>;

export const entityPages = {
  organizations: page(organization),
  employees: page(employee),
  customers: page(customer),
  deals: page(deal),
  projects: page(project),
  support_tickets: page(supportTicket),
  documents: page(document),
} as const satisfies Record<EntityType, z.ZodType>;

export type EntityRecord<T extends EntityType> = z.infer<(typeof entityRecords)[T]>;
export type Customer = z.infer<typeof customer>;
export type Document = z.infer<typeof document>;
