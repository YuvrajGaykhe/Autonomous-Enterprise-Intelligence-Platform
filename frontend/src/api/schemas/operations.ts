/**
 * Health, sources, ingestion runs and metrics (DERIVED from `app/api/v1/schemas.py`).
 */

import { z } from 'zod';

import { count, isoDateTime, page, uuid } from './common';

export const healthResponse = z.strictObject({
  status: z.enum(['healthy', 'unhealthy']),
  service: z.string(),
  version: z.string(),
  checks: z.strictObject({ database: z.enum(['ok', 'unavailable']) }),
});

export const sourceSummary = z.strictObject({
  source: z.string(),
  source_type: z.string(),
  capabilities: z.strictObject({
    supported_entity_types: z.array(z.string()),
    supports_incremental: z.boolean(),
    supports_health_check: z.boolean(),
    read_only: z.boolean(),
  }),
});

export const sourceListResponse = z.strictObject({ sources: z.array(sourceSummary) });

export const sourceHealthResponse = z.strictObject({
  source: z.string(),
  status: z.enum(['healthy', 'unhealthy', 'unsupported']),
  latency_ms: z.number().nonnegative().nullable(),
  error_type: z.string().nullable(),
  checked_at: isoDateTime,
});

export const runStatus = z.enum(['RUNNING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED', 'NOOP']);

const runFields = {
  run_id: uuid,
  source_system: z.string(),
  source_entity: z.string().nullable(),
  mode: z.string(),
  status: runStatus,
  started_at: isoDateTime,
  finished_at: isoDateTime.nullable(),
  records_fetched: count,
  records_raw_persisted: count,
  records_inserted: count,
  records_updated: count,
  records_unchanged: count,
  records_rejected: count,
  records_failed: count,
  warnings: count,
  batches_failed: count,
  error_summary: z.string().nullable(),
};

export const ingestionRunResponse = z.strictObject(runFields);
export const runListResponse = page(ingestionRunResponse);

export const entityRunResult = z.strictObject({
  entity_type: z.string(),
  status: z.enum(['completed', 'failed', 'skipped']),
  records_fetched: count,
  records_inserted: count,
  records_updated: count,
  records_unchanged: count,
  records_rejected: count,
  records_failed: count,
  warnings: count,
  batches_committed: count,
  batches_failed: count,
  failure: z.string().nullable(),
});

export const ingestionRunCreatedResponse = z.strictObject({
  ...runFields,
  batches_committed: count,
  entities: z.array(entityRunResult),
});

const errorSeverity = z.enum(['ERROR', 'WARNING', 'INFO']);

export const ingestionErrorResponse = z.strictObject({
  id: uuid,
  severity: errorSeverity,
  code: z.string().nullable(),
  message: z.string(),
  source_system: z.string().nullable(),
  source_entity: z.string().nullable(),
  source_id: z.string().nullable(),
  created_at: isoDateTime,
  findings: z.array(
    z.strictObject({
      code: z.string(),
      field_name: z.string().nullable(),
      severity: errorSeverity.nullable(),
      message: z.string(),
    }),
  ),
});

export const errorListResponse = page(ingestionErrorResponse);

const runStatusCounts = z.strictObject({
  RUNNING: count,
  SUCCESS: count,
  PARTIAL_SUCCESS: count,
  FAILED: count,
  NOOP: count,
});

const runReference = z.strictObject({
  run_id: uuid,
  status: runStatus,
  started_at: isoDateTime,
  finished_at: isoDateTime.nullable(),
});

const metricsFields = {
  runs_total: count,
  runs_by_status: runStatusCounts,
  records_fetched_total: count,
  records_raw_persisted_total: count,
  records_inserted_total: count,
  records_updated_total: count,
  records_unchanged_total: count,
  records_rejected_total: count,
  records_failed_total: count,
  warnings_total: count,
  batches_failed_total: count,
  errors_by_severity: z.strictObject({ ERROR: count, WARNING: count, INFO: count }),
  connector_request_failures_total: count,
  validation_errors_total: count,
  ingestion_duration_seconds_total: z.number().nonnegative(),
  canonical_records: z.strictObject({
    organizations: count,
    employees: count,
    customers: count,
    deals: count,
    projects: count,
    support_tickets: count,
    documents: count,
  }),
};

export const ingestionMetricsResponse = z.strictObject({
  totals: z.strictObject(metricsFields),
  sources: z.array(
    z.strictObject({
      ...metricsFields,
      source_system: z.string(),
      last_run: runReference.nullable(),
      last_successful_run: runReference.nullable(),
    }),
  ),
  process: z.strictObject({
    started_at: isoDateTime,
    runs_total: count,
    runs_by_status: runStatusCounts,
    records_fetched_total: count,
    records_inserted_total: count,
    records_updated_total: count,
    records_unchanged_total: count,
    records_rejected_total: count,
    connector_request_failures_total: count,
    validation_errors_total: count,
    ingestion_duration_seconds: z.strictObject({ count, sum: z.number().nonnegative() }),
  }),
});

export type HealthResponse = z.infer<typeof healthResponse>;
export type SourceListResponse = z.infer<typeof sourceListResponse>;
export type SourceHealthResponse = z.infer<typeof sourceHealthResponse>;
export type IngestionRunResponse = z.infer<typeof ingestionRunResponse>;
export type IngestionRunCreatedResponse = z.infer<typeof ingestionRunCreatedResponse>;
export type IngestionMetricsResponse = z.infer<typeof ingestionMetricsResponse>;
