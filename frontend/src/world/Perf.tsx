/**
 * `?perf=1` (spec §9.10): the frame time and draw calls of the last 30 seconds, measured in the
 * page, shown over the office and readable by the performance-record tool.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef, useState } from 'react';

import { PERF_BUDGET, recent, summarize, type FrameSample, type PerfSummary } from '@/domain/perf';

/** What the page measured; the record tool reads it as `window.aiceohqPerf`. */
interface PerfRecord {
  samples: FrameSample[];
  renderer: string;
  summary: () => PerfSummary | null;
}

declare global {
  interface Window {
    aiceohqPerf?: PerfRecord;
  }
}

const record: PerfRecord = {
  samples: [],
  renderer: 'unknown',
  summary: () => summarize(recent(record.samples, performance.now())),
};

/** Counts every draw call of a frame, whatever renders it: the pixel pass makes several. */
export function PerfProbe() {
  const gl = useThree((state) => state.gl);
  const previous = useRef<number | null>(null);

  useEffect(() => {
    gl.info.autoReset = false;
    const context = gl.getContext();
    const debug = context.getExtension('WEBGL_debug_renderer_info');
    record.renderer =
      debug === null ? 'unknown' : String(context.getParameter(debug.UNMASKED_RENDERER_WEBGL));
    record.samples = [];
    window.aiceohqPerf = record;
    return () => {
      gl.info.autoReset = true;
      delete window.aiceohqPerf;
    };
  }, [gl]);

  useFrame(() => {
    const now = performance.now();
    if (previous.current !== null) {
      record.samples.push({
        at: now,
        frameMs: now - previous.current,
        drawCalls: gl.info.render.calls,
        triangles: gl.info.render.triangles,
      });
      if (record.samples.length > 4000) record.samples = recent(record.samples, now);
    }
    previous.current = now;
    gl.info.reset();
  }, -100);

  return null;
}

const ms = (value: number) => `${value.toFixed(1)} ms`;

export function PerfOverlay() {
  const [summary, setSummary] = useState<PerfSummary | null>(null);
  useEffect(() => {
    const timer = window.setInterval(() => setSummary(record.summary()), 500);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div
      role="status"
      aria-label="Frame time"
      data-testid="perf"
      className="pointer-events-none absolute top-3 right-3 z-30 rounded-lg bg-black/80 px-3 py-2 font-mono text-xs text-white"
    >
      {summary === null ? (
        <p>Measuring…</p>
      ) : (
        <>
          <p>
            frame median {ms(summary.medianMs)} · p95 {ms(summary.p95Ms)}
          </p>
          <p>
            draw calls {summary.maxDrawCalls} (budget {PERF_BUDGET.drawCalls}) · triangles{' '}
            {summary.maxTriangles}
          </p>
          <p>
            {summary.frames} frames over {(summary.spanMs / 1000).toFixed(1)} s ·{' '}
            {summary.within ? 'within budget' : 'OVER budget'}
          </p>
          <p className="max-w-80 truncate text-white/70">{record.renderer}</p>
        </>
      )}
    </div>
  );
}
