/**
 * Evidence targets (spec §8.4): the Layer 1 record an evidence item or an entity reference names.
 *
 * Payload references carry an entity type and a source id; the record is found in that type's
 * `GET /entities/{type}` list by its source system and source id. Every field is shown as the API
 * stated it, with no value reformatted.
 */

import { ENTITY_TYPES, type EntityType } from '@/api/schemas/entities';

/** The entity list a reference's `entity` names, or null for one this frontend cannot open. */
export function entityTypeOf(entity: string): EntityType | null {
  return (ENTITY_TYPES as readonly string[]).includes(entity) ? (entity as EntityType) : null;
}

interface SourceKeyed {
  source_system: string;
  source_id: string;
}

export function findRecord<T extends SourceKeyed>(
  records: readonly T[],
  sourceSystem: string,
  sourceId: string,
): T | null {
  return (
    records.find(
      (record) => record.source_system === sourceSystem && record.source_id === sourceId,
    ) ?? null
  );
}

export interface RecordField {
  name: string;
  value: string;
}

/** Every field of a record, in the API's key order, as text; null reads `null`. */
export function recordFields(record: object): RecordField[] {
  return Object.entries(record).map(([name, value]) => ({
    name,
    value: value === null ? 'null' : typeof value === 'string' ? value : JSON.stringify(value),
  }));
}
