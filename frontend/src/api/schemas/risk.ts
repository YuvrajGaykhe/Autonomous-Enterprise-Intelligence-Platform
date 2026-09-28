/**
 * Risk assessments, briefs and decisions (DERIVED from `app/api/v1/schemas.py`, VS-01 M8).
 */

import { z } from 'zod';

import {
  citation,
  evidence,
  rankingKey,
  riskBand,
  signals,
  businessFunction,
  stance,
  actionId,
} from './briefPayloadV1';
import { count, integer, isoDate, isoDateTime, page, sha256Hex, uuid } from './common';

export const assessmentRunRequest = z.strictObject({
  as_of: isoDate.nullable(),
  source_system: z.string(),
});

export const assessmentRunResponse = z.strictObject({
  items: z.array(
    z.strictObject({
      assessment_id: uuid,
      created: z.boolean(),
      brief_id: uuid.nullable(),
      payload_hash: sha256Hex.nullable(),
    }),
  ),
});

const assessmentFields = {
  id: uuid,
  customer_source_id: z.string().nullable(),
  as_of: isoDate,
  source_system: z.string(),
  layer1_fingerprint: sha256Hex,
  rules_version: integer,
  linker_version: z.string(),
  band: riskBand,
  executive_worthy: z.boolean(),
  ranking_key: rankingKey,
};

export const assessmentListItem = z.strictObject({
  ...assessmentFields,
  brief_ids: z.array(uuid),
});

export const assessmentListResponse = page(assessmentListItem);

export const assessmentPosition = z.strictObject({
  ordinal: count,
  function: businessFunction,
  stance,
  proposed_action: actionId,
  object_ref: z.string(),
  rationale: z.string(),
  citations: z.array(evidence),
});

export const assessmentDetailResponse = z.strictObject({
  ...assessmentFields,
  satisfied_rules: z.array(z.string()),
  signals,
  positions: z.array(assessmentPosition),
  briefs: z.array(
    z.strictObject({
      id: uuid,
      policy_version: integer,
      template_version: z.string(),
      payload_hash: sha256Hex,
    }),
  ),
});

export const decisionStatus = z.enum(['PENDING', 'APPROVED', 'REJECTED']);
export const decision = z.enum(['APPROVED', 'REJECTED']);

/**
 * A stored brief. `payload` is checked here only as an object with a version; the version
 * decides which schema parses it (`parseBrief` in `src/api/risk.ts`, §6.4).
 */
export const briefResponse = z.strictObject({
  id: uuid,
  assessment_id: uuid,
  status: z.string(),
  decision_status: decisionStatus,
  policy_version: integer,
  template_version: z.string(),
  payload_hash: sha256Hex,
  payload: z.looseObject({ payload_version: integer }),
  narrative: z.string(),
  citations: z.array(citation),
});

export const decisionRequest = z.strictObject({
  actor: z.string().min(1).max(255),
  decision,
  note: z.string().max(2000).nullable(),
  payload_hash: sha256Hex,
  supersedes_id: uuid.nullable(),
});

export const decisionResponse = z.strictObject({
  id: uuid,
  brief_id: uuid,
  payload_hash: sha256Hex,
  actor: z.string(),
  decision,
  note: z.string().nullable(),
  decided_at: isoDateTime,
  supersedes_id: uuid.nullable(),
});

export const decisionHistoryResponse = z.strictObject({ items: z.array(decisionResponse) });

export type AssessmentRunRequest = z.infer<typeof assessmentRunRequest>;
export type AssessmentRunResponse = z.infer<typeof assessmentRunResponse>;
export type AssessmentListItem = z.infer<typeof assessmentListItem>;
export type AssessmentDetail = z.infer<typeof assessmentDetailResponse>;
export type BriefResponse = z.infer<typeof briefResponse>;
export type DecisionRequest = z.infer<typeof decisionRequest>;
export type DecisionResponse = z.infer<typeof decisionResponse>;
