/**
 * Every Zod response schema is at least as strict as the API's own OpenAPI schema: its output
 * type is assignable to the type openapi-typescript generated from the recorded `/openapi.json`.
 * The check happens when `tsc` type-checks this file; the test only makes it a counted test.
 */

import { describe, expect, it } from 'vitest';
import type { z } from 'zod';

import type { components } from '@/api/generated/openapi';
import type { entityPages } from '@/api/schemas/entities';
import type {
  errorListResponse,
  healthResponse,
  ingestionMetricsResponse,
  ingestionRunCreatedResponse,
  ingestionRunResponse,
  runListResponse,
  sourceHealthResponse,
  sourceListResponse,
} from '@/api/schemas/operations';
import type {
  assessmentDetailResponse,
  assessmentListResponse,
  assessmentRunRequest,
  assessmentRunResponse,
  briefResponse,
  decisionHistoryResponse,
  decisionRequest,
  decisionResponse,
} from '@/api/schemas/risk';

type Schemas = components['schemas'];
type Out<S extends z.ZodType> = z.infer<S>;
/** True only when From is assignable to To (no distribution over unions). */
type Assignable<From, To> = [From] extends [To] ? true : false;

const checks = {
  health: true satisfies Assignable<Out<typeof healthResponse>, Schemas['HealthResponse']>,
  sources: true satisfies Assignable<Out<typeof sourceListResponse>, Schemas['SourceListResponse']>,
  sourceHealth: true satisfies Assignable<
    Out<typeof sourceHealthResponse>,
    Schemas['SourceHealthResponse']
  >,
  run: true satisfies Assignable<Out<typeof ingestionRunResponse>, Schemas['IngestionRunResponse']>,
  runs: true satisfies Assignable<Out<typeof runListResponse>, Schemas['RunListResponse']>,
  runCreated: true satisfies Assignable<
    Out<typeof ingestionRunCreatedResponse>,
    Schemas['IngestionRunCreatedResponse']
  >,
  runErrors: true satisfies Assignable<Out<typeof errorListResponse>, Schemas['ErrorListResponse']>,
  metrics: true satisfies Assignable<
    Out<typeof ingestionMetricsResponse>,
    Schemas['IngestionMetricsResponse']
  >,
  organizations: true satisfies Assignable<
    Out<(typeof entityPages)['organizations']>,
    Schemas['OrganizationListResponse']
  >,
  employees: true satisfies Assignable<
    Out<(typeof entityPages)['employees']>,
    Schemas['EmployeeListResponse']
  >,
  customers: true satisfies Assignable<
    Out<(typeof entityPages)['customers']>,
    Schemas['CustomerListResponse']
  >,
  deals: true satisfies Assignable<Out<(typeof entityPages)['deals']>, Schemas['DealListResponse']>,
  projects: true satisfies Assignable<
    Out<(typeof entityPages)['projects']>,
    Schemas['ProjectListResponse']
  >,
  tickets: true satisfies Assignable<
    Out<(typeof entityPages)['support_tickets']>,
    Schemas['SupportTicketListResponse']
  >,
  documents: true satisfies Assignable<
    Out<(typeof entityPages)['documents']>,
    Schemas['DocumentListResponse']
  >,
  assessmentRun: true satisfies Assignable<
    Out<typeof assessmentRunResponse>,
    Schemas['AssessmentRunResponse']
  >,
  assessmentRunRequest: true satisfies Assignable<
    Out<typeof assessmentRunRequest>,
    Schemas['AssessmentRunRequest']
  >,
  assessments: true satisfies Assignable<
    Out<typeof assessmentListResponse>,
    Schemas['AssessmentListResponse']
  >,
  assessment: true satisfies Assignable<
    Out<typeof assessmentDetailResponse>,
    Schemas['AssessmentDetailResponse']
  >,
  brief: true satisfies Assignable<Out<typeof briefResponse>, Schemas['BriefResponse']>,
  decisionRequest: true satisfies Assignable<
    Out<typeof decisionRequest>,
    Schemas['DecisionRequest']
  >,
  decision: true satisfies Assignable<Out<typeof decisionResponse>, Schemas['DecisionResponse']>,
  decisions: true satisfies Assignable<
    Out<typeof decisionHistoryResponse>,
    Schemas['DecisionHistoryResponse']
  >,
};

describe('the Zod schemas against the generated OpenAPI types', () => {
  it('type-check as assignable for every route the frontend calls', () => {
    expect(Object.values(checks).every(Boolean)).toBe(true);
    expect(Object.keys(checks)).toHaveLength(23);
  });
});
