/**
 * Fixed copy (spec Appendix A; D-F-1, D-F-2, D-F-7, D-F-13).
 *
 * Every Appendix A string lives here exactly once, and every surface renders it from here. A
 * guard test reads Appendix A from the specification and checks both. `{name}` marks a value
 * the surface fills in; `fill` substitutes it.
 */

export const COPY = {
  productName: 'AI CEO HQ',
  decisionDisclaimer: 'Identity is recorded, not authenticated. Nothing is executed.',
  aboutAgents:
    "These agents are the system's rule-based components. In VS-01, no language model, embedding or prompt produces any part of a brief.",
  bandLegend: 'A band is a policy artefact, not a probability.',
  replayBanner: 'Replay of recorded results · as_of {date}',
  alreadyAssessedBanner: 'Already assessed: replaying recorded results',
  unknownOutcome: 'The result is unknown. Checking what was recorded…',
  emptyDecisionChain: 'No decisions recorded for this brief yet.',
  inboxNoBrief: 'No customer is at WATCH or above on this date.',
  inboxNoAssessment: 'No assessment exists for this date yet. Run one from the top bar.',
  memoryNoRecords: 'No records yet: run an ingestion first.',
  unsupportedBrief: 'This brief uses payload version {n}, which this frontend does not support.',
  webglFallback:
    'The 3D office could not start on this device, so you are in Classic view. Every panel works the same.',
  mockSourceHostedOnly: 'This mock source runs in local mode only.',
  lockedRoom: 'Opens with VS-0{n}',
} as const;

/** Agent role lines for panel headers (Appendix A). */
export const ROLE_LINES = {
  connector: 'Fetches records from one configured source into Layer 1.',
  memory: 'Holds the canonical Layer 1 records every agent reads.',
  linker: 'Links documents to customers by exact id and exact name.',
  signals: "Computes each customer's signals and risk band.",
  sales: 'States the commercial position on each customer.',
  support: 'States the support position on each customer.',
  reconciler: 'Resolves conflicting positions by a named policy, and keeps the dissent.',
  briefWriter: 'Writes the cited brief the CEO decides on.',
  ceo: 'You decide. The system recommends; nothing is executed.',
} as const;

/** Substitute `{name}` markers. A marker without a value is left as it is. */
export function fill(template: string, values: Readonly<Record<string, string | number>>): string {
  return template.replace(/\{(\w+)\}/g, (marker, name: string) =>
    name in values ? String(values[name]) : marker,
  );
}
