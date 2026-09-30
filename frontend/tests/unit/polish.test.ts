/**
 * F6's pure parts: the tour's steps and its first-visit rule (`src/domain/tour.ts`), and the pixel
 * art's pictures and their runs (`src/states/art.tsx`).
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { COPY } from '@/copy';
import { moveStep, TOUR_SEEN, TOUR_STEPS, tourOpensOnArrival } from '@/domain/tour';
import { ART, runsOf } from '@/states/art';

import { REPO_ROOT } from '../support/fixtures';

describe('the tour (F6)', () => {
  it('has three steps, one per spot: the agents, the run and the inbox', () => {
    expect(TOUR_STEPS.map((step) => step.spot)).toEqual(['agents', 'run', 'inbox']);
    expect(new Set(TOUR_STEPS.map((step) => step.title)).size).toBe(3);
  });

  it('opens on arrival until this browser has seen it', () => {
    expect(tourOpensOnArrival(null)).toBe(true);
    expect(tourOpensOnArrival('')).toBe(true);
    expect(tourOpensOnArrival(TOUR_SEEN)).toBe(false);
  });

  it('moves between steps and never past either end', () => {
    expect(moveStep(0, 1)).toBe(1);
    expect(moveStep(1, 1)).toBe(2);
    expect(moveStep(2, 1)).toBe(2);
    expect(moveStep(2, -1)).toBe(1);
    expect(moveStep(0, -1)).toBe(0);
  });

  it('claims nothing the system does not do (§11): no model, no score, no execution', () => {
    const copy = TOUR_STEPS.map((step) => `${step.title} ${step.body}`).join(' ');
    expect(copy).not.toMatch(/\b(?:AI|LLM|GPT|intelligen|smart|learn|predict|probab|score)/i);
    expect(copy).toContain('rule-based');
    expect(copy).toContain('nothing is executed');
    expect(copy).toContain('replay its recorded results under a banner');
  });

  it('repeats no Appendix A string, so each stays exactly once in src/ (§12.4)', () => {
    const copy = TOUR_STEPS.map((step) => step.body).join(' ');
    for (const text of Object.values(COPY)) expect(copy).not.toContain(text);
  });

  it('is named in the specification as the §8.2 "?" tour', () => {
    const spec = readFileSync(`${REPO_ROOT}CONTEXT/FRONTEND_SPECIFICATION.md`, 'utf8');
    expect(spec).toContain('and a "?" tour');
  });
});

describe('the pixel art (F6)', () => {
  it.each(Object.entries(ART))('%s is a rectangle drawn in the palette', (_, rows) => {
    const width = rows[0]?.length ?? 0;
    expect(width).toBeGreaterThan(0);
    for (const row of rows) {
      expect(row).toHaveLength(width);
      expect(row).toMatch(/^[.kwWcopgGsnbrye]+$/);
    }
  });

  it('draws each row as runs of one colour, and leaves the dots empty', () => {
    expect(runsOf(['kkw.', '.bb.'])).toEqual([
      { x: 0, y: 0, width: 2, fill: 'currentColor' },
      { x: 2, y: 0, width: 1, fill: '#c8894f' },
      { x: 1, y: 1, width: 2, fill: '#22d3ee' },
    ]);
  });

  it('keeps every picture free of image files: the art is code', () => {
    const source = readFileSync(resolve(import.meta.dirname, '../../src/states/art.tsx'), 'utf8');
    expect(source).not.toMatch(/\.(?:png|gif|jpe?g|webp)\b/);
  });
});
