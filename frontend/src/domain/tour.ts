/**
 * The three-step tour (spec §8.2's "?" tour; F6). It opens once per browser on the first visit,
 * and the HUD's "?" opens it again at any time (owner ruling, F6). Each step points at one part of
 * the page, its spot, which both views have: the agents, the Run assessment control, and the CEO
 * inbox.
 *
 * The copy is PROPOSED. It states only what the system does: rule-based agents, work shown only
 * during a real request or a bannered replay, and a decision that is recorded but executes nothing
 * (§11).
 */

export type TourSpot = 'agents' | 'run' | 'inbox';

export interface TourStep {
  spot: TourSpot;
  title: string;
  body: string;
}

export const TOUR_STEPS: readonly TourStep[] = [
  {
    spot: 'agents',
    title: 'Meet the agents',
    body: "Each agent is one of the system's rule-based components. Open one, in the office or from the staff directory, to see its real output and the API calls behind it.",
  },
  {
    spot: 'run',
    title: 'Watch a run',
    body: 'Run assessment asks the API to assess every customer on the chosen date. In the office, agents work only while that request is in flight, then replay its recorded results under a banner. Replay shows them again.',
  },
  {
    spot: 'inbox',
    title: 'Decide as the CEO',
    body: "The CEO inbox holds every brief, executive-worthy ones first. Read a brief's cited evidence, then approve or reject the whole brief with a note. The decision is recorded; nothing is executed.",
  },
];

/** What `aiceohq.tour` holds once the reader has closed the tour (§11). */
export const TOUR_SEEN = 'seen';

/** The tour opens on arrival until the reader has closed it once in this browser. */
export function tourOpensOnArrival(stored: string | null): boolean {
  return stored !== TOUR_SEEN;
}

/** The step `index` moves to by `delta`, kept inside the tour. */
export function moveStep(index: number, delta: number): number {
  return Math.min(Math.max(index + delta, 0), TOUR_STEPS.length - 1);
}
