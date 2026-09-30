/**
 * The performance record (spec §9.10): frame times and draw calls over the last 30 seconds, as
 * `?perf=1` shows them, against the budget.
 */

export const PERF_WINDOW_MS = 30_000;

export const PERF_BUDGET = { medianMs: 16.7, p95Ms: 25, drawCalls: 150 } as const;

/**
 * A frame time at the budget's resolution. Frame times are differences of timestamps, so a 16.7 ms
 * frame can come out as 16.700000000000728 and fail `<= 16.7` on floating-point noise alone.
 */
function atResolution(ms: number): number {
  return Math.round(ms * 100) / 100;
}

export interface FrameSample {
  /** When the frame began, in milliseconds. */
  at: number;
  /** The time since the previous frame began. */
  frameMs: number;
  drawCalls: number;
  triangles: number;
}

/** The nearest-rank percentile `p` (0–100) of `values`; NaN for no values. */
export function percentile(values: readonly number[], p: number): number {
  if (values.length === 0) return Number.NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.min(sorted.length, Math.max(1, Math.ceil((p / 100) * sorted.length)));
  return sorted[rank - 1] as number;
}

/** The samples of the last `windowMs` before `now`. */
export function recent(
  samples: readonly FrameSample[],
  now: number,
  windowMs = PERF_WINDOW_MS,
): FrameSample[] {
  return samples.filter((sample) => now - sample.at <= windowMs);
}

export interface PerfSummary {
  frames: number;
  spanMs: number;
  medianMs: number;
  p95Ms: number;
  maxDrawCalls: number;
  medianDrawCalls: number;
  maxTriangles: number;
  within: boolean;
}

export function summarize(samples: readonly FrameSample[]): PerfSummary | null {
  const [first] = samples;
  const last = samples.at(-1);
  if (first === undefined || last === undefined) return null;
  const frames = samples.map((sample) => sample.frameMs);
  const calls = samples.map((sample) => sample.drawCalls);
  const summary = {
    frames: samples.length,
    spanMs: last.at - first.at,
    medianMs: percentile(frames, 50),
    p95Ms: percentile(frames, 95),
    maxDrawCalls: Math.max(...calls),
    medianDrawCalls: percentile(calls, 50),
    maxTriangles: Math.max(...samples.map((sample) => sample.triangles)),
  };
  return {
    ...summary,
    within:
      atResolution(summary.medianMs) <= PERF_BUDGET.medianMs &&
      atResolution(summary.p95Ms) <= PERF_BUDGET.p95Ms &&
      summary.maxDrawCalls <= PERF_BUDGET.drawCalls,
  };
}
