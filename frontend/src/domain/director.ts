/**
 * The Director (spec §9.4–§9.6, D-F-1, AC-F-2; the owner's F4 ruling on how agents move).
 *
 * It turns a show into a timeline: for each agent, from moment to moment, its state, where it
 * should be, its caption and whether it carries a sheet; plus the arrows and the CEO's tray.
 *
 * - **Live:** while a POST is in flight, its stages' agents go to their desks and WORK in stage
 *   order, captioned `ASSESSING…` or `INGESTING…`. No other value exists yet.
 * - **Hold:** after the POST returns and before its replay starts, they wait at their desks, idle.
 * - **Replay:** an episode's steps, in order. Everyone in the episode first walks to their desk. An
 *   agent WORKS at its desk; a finished stage **walks its result to the next stage's agent**, the
 *   arrow and its label being the result's own caption; the analysts meet at the debate table for
 *   a conflict; BRIEF_WRITER walks the briefs to the CEO's tray, one sheet per inbox row. When all
 *   is done they cheer, and the show ends.
 *
 * Outside a show every agent is idle, in the Break Area. WORKING and HANDOFF occur only in a live
 * or a replay timeline, and a replay is always shown under its banner (the page's part).
 *
 * The timeline is pure: walk durations come from the walk grid, so the same episode always plays
 * the same way. Times are seconds from the show's start.
 */

import type { AgentState } from './agentLook';
import { participants, type Episode, type Step } from './episodes';
import { debateSeat, visitPoint, type Seat } from './floorPlan';
import type { Agent } from './roster';
import type { Point } from './walkGrid';

/** Where an agent should be. */
export type Place =
  | { kind: 'break' }
  | { kind: 'desk' }
  | { kind: 'visit'; agentIds: readonly string[] }
  | { kind: 'debate'; seat: number };

type VisitPlace = Extract<Place, { kind: 'visit' }>;
type DebatePlace = Extract<Place, { kind: 'debate' }>;

export interface Directive {
  state: AgentState;
  place: Place;
  caption: string | null;
  /** Carrying a sheet to someone (a hand-off or a delivery). */
  carrying: boolean;
  /** The last beat: everyone cheers where they stand. */
  cheer: boolean;
  /** When a walk should be over, in show seconds; the walker hurries to make it. */
  arriveBy: number | null;
}

export interface Arrow {
  id: string;
  from: Point;
  to: Point;
  tone: 'handoff' | 'conflict';
  label: string;
}

interface Cue {
  start: number;
  end: number;
  directive: Directive;
}

interface ArrowSpan {
  start: number;
  end: number;
  arrow: Arrow;
}

export interface Timeline {
  /** How long the show lasts; Infinity for live and hold, which end when their request does. */
  duration: number;
  cues: ReadonlyMap<string, readonly Cue[]>;
  arrows: readonly ArrowSpan[];
  /** When each sheet lands in the CEO's tray; empty when the show delivers nothing. */
  tray: readonly { start: number; count: number }[];
}

export interface Frame {
  directives: ReadonlyMap<string, Directive>;
  arrows: readonly Arrow[];
  /** The tray's sheets while a show fills it; null leaves the tray to the inbox. */
  trayCount: number | null;
  ended: boolean;
}

/** Beat lengths, in seconds (PROPOSED). */
export const BEATS = {
  /** An agent at work on one step. */
  work: 1.8,
  /** A hand-off after the walk: the result changes hands. */
  handover: 0.9,
  /** The two sides of a conflict, face to face. */
  conflict: 2.2,
  /** One sheet into the tray. */
  deliver: 1.1,
  /** The CEO's tray, full. */
  tray: 1,
  /** Everyone cheers. */
  cheer: 2.4,
  /** Between two agents lighting up in a live run. */
  liveStagger: 0.35,
  /** The least time a gather takes, even when everyone is already seated. */
  minimumGather: 0.6,
} as const;

/** What the Director needs of the office: every agent's place, and how long a walk takes. */
export interface Layout {
  roster: readonly Agent[];
  seats: ReadonlyMap<string, Seat>;
  walkSeconds: (from: Point, to: Point) => number;
}

const at = (seat: Seat): Point => [seat.x, seat.z];

function middle(points: readonly Point[]): Point {
  const count = Math.max(1, points.length);
  return [
    points.reduce((sum, point) => sum + point[0], 0) / count,
    points.reduce((sum, point) => sum + point[1], 0) / count,
  ];
}

function kindOf(layout: Layout, agentId: string): Agent['kind'] {
  return layout.roster.find((agent) => agent.id === agentId)?.kind ?? 'connector';
}

function seatOf(layout: Layout, agentId: string): Seat {
  return layout.seats.get(agentId) ?? { x: 0, z: 0, facing: 0, pose: 'stand' };
}

/** The point and facing of a place other than the Break Area, whose places the world hands out. */
export function placeSeat(
  layout: Layout,
  agentId: string,
  place: Exclude<Place, { kind: 'break' }>,
): Seat {
  switch (place.kind) {
    case 'desk':
      return seatOf(layout, agentId);
    case 'debate':
      return debateSeat(place.seat);
    case 'visit': {
      const points = place.agentIds.map((id) => visitPoint(kindOf(layout, id), seatOf(layout, id)));
      const first = points[0] ?? seatOf(layout, agentId);
      return {
        ...first,
        x: points.reduce((sum, point) => sum + point.x, 0) / Math.max(1, points.length),
        z: points.reduce((sum, point) => sum + point.z, 0) / Math.max(1, points.length),
      };
    }
  }
}

const idleAtDesk: Directive = {
  state: 'IDLE',
  place: { kind: 'desk' },
  caption: null,
  carrying: false,
  cheer: false,
  arriveBy: null,
};

interface Track {
  cues: Cue[];
  /** What the agent does whenever it has nothing to play. */
  resting: Directive;
  /** How far its cues reach. */
  until: number;
}

/** Builds per-agent cues without gaps: between its own beats an agent keeps its resting cue. */
class Score {
  readonly tracks = new Map<string, Track>();
  readonly arrows: ArrowSpan[] = [];
  readonly tray: { start: number; count: number }[] = [];

  constructor(agents: readonly string[], resting: Directive) {
    for (const agent of agents) this.tracks.set(agent, { cues: [], resting, until: 0 });
  }

  private track(agent: string): Track {
    return this.tracks.get(agent) as Track;
  }

  private static push(track: Track, start: number, end: number, directive: Directive): void {
    if (end <= start) return;
    track.cues.push({ start, end, directive });
    track.until = end;
  }

  /** `agent` follows `directive` from `start` to `end`, resting until then. */
  play(agent: string, start: number, end: number, directive: Directive): void {
    const track = this.track(agent);
    if (start > track.until) Score.push(track, track.until, start, track.resting);
    Score.push(track, Math.max(start, track.until), end, directive);
  }

  /** From `from` on, whenever it has nothing to play, `agent` rests like this. */
  rest(agent: string, directive: Directive, from: number): void {
    const track = this.track(agent);
    if (from > track.until) Score.push(track, track.until, from, track.resting);
    track.resting = directive;
  }

  restingOf(agent: string): Directive {
    return this.track(agent).resting;
  }

  /** Fill every agent's cues up to `end` with its resting cue. */
  finish(end: number): void {
    for (const track of this.tracks.values())
      if (end > track.until) Score.push(track, track.until, end, track.resting);
  }

  get cues(): Map<string, Cue[]> {
    return new Map([...this.tracks].map(([agent, track]) => [agent, track.cues]));
  }
}

function directive(state: AgentState, place: Place, extra: Partial<Directive> = {}): Directive {
  return { ...idleAtDesk, state, place, ...extra };
}

/** A live run: its agents walk to their desks and light up in stage order (§9.6). */
export function liveTimeline(agents: readonly string[], caption: string): Timeline {
  const score = new Score(agents, idleAtDesk);
  agents.forEach((agent, index) => {
    score.play(
      agent,
      index * BEATS.liveStagger,
      Infinity,
      directive('WORKING', { kind: 'desk' }, { caption }),
    );
  });
  return { duration: Infinity, cues: score.cues, arrows: [], tray: [] };
}

/** Between a POST's answer and its replay: its agents wait at their desks, idle. */
export function holdTimeline(agents: readonly string[]): Timeline {
  const score = new Score(agents, idleAtDesk);
  score.finish(Infinity);
  return { duration: Infinity, cues: score.cues, arrows: [], tray: [] };
}

/** Consecutive steps of one stage, split wherever an agent would have to be in two places. */
function groups(steps: readonly Step[]): Step[][] {
  const result: Step[][] = [];
  for (const step of steps) {
    const last = result.at(-1);
    const head = last?.[0];
    if (last !== undefined && head !== undefined && head.stage === step.stage) last.push(step);
    else result.push([step]);
  }
  return result;
}

/** The agents a group's result goes to next: the next group's actors, the CEO excepted. */
function receivers(next: Step[] | undefined): string[] {
  if (next === undefined) return [];
  return [...new Set(next.flatMap((step) => step.agents))].filter((agent) => agent !== 'ceo');
}

function lastCaptions(group: readonly Step[]): Map<string, string> {
  const captions = new Map<string, string>();
  for (const step of group) for (const agent of step.agents) captions.set(agent, step.caption);
  return captions;
}

/**
 * A replay of `episode` (§9.5, §9.6). `gather` is how long everyone has to reach their desk
 * first: a full walk from the Break Area, or less after a live run already seated them.
 */
export function replayTimeline(episode: Episode, layout: Layout, gather: number): Timeline {
  const cast = participants(episode);
  const score = new Score(cast, idleAtDesk);
  const done = directive('DONE', { kind: 'desk' });
  const desk = (agent: string) => at(seatOf(layout, agent));
  let t = Math.max(BEATS.minimumGather, gather);
  for (const agent of cast)
    score.play(agent, 0, t, directive('IDLE', { kind: 'desk' }, { arriveBy: t }));
  let arrowCount = 0;
  const arrow = (start: number, end: number, value: Omit<Arrow, 'id'>) => {
    arrowCount += 1;
    score.arrows.push({ start, end, arrow: { id: `arrow-${arrowCount}`, ...value } });
  };

  const sequence = groups(episode.steps);
  sequence.forEach((group, index) => {
    const first = group[0] as Step;
    const kind = first.kind;
    const next = sequence[index + 1];

    if (kind === 'work') {
      // Steps of one stage whose agents differ play together; an agent's second step follows. A
      // slot is only ever flushed with a step in it.
      let slot: Step[] = [];
      const flush = () => {
        for (const step of slot)
          for (const agent of step.agents)
            score.play(
              agent,
              t,
              t + BEATS.work,
              directive('WORKING', { kind: 'desk' }, { caption: step.caption }),
            );
        t += BEATS.work;
        slot = [];
      };
      for (const step of group) {
        if (slot.some((other) => other.agents.some((agent) => step.agents.includes(agent))))
          flush();
        slot.push(step);
      }
      flush();

      // The owner's F4 ruling: a finished stage walks its result to the next stage's agents. The
      // analysts are the exception when a conflict follows: the conflict itself walks them over.
      const to = receivers(next);
      const givers = [...lastCaptions(group).entries()].filter(([agent]) => !to.includes(agent));
      if (to.length > 0 && givers.length > 0 && next?.[0]?.kind !== 'conflict') {
        const place: VisitPlace = { kind: 'visit', agentIds: to };
        const walk = Math.max(
          ...givers.map(([agent]) =>
            layout.walkSeconds(desk(agent), at(placeSeat(layout, agent, place))),
          ),
        );
        const end = t + walk + BEATS.handover;
        for (const [agent, caption] of givers) {
          score.play(
            agent,
            t,
            end,
            directive('HANDOFF', place, { caption, carrying: true, arriveBy: t + walk }),
          );
          arrow(t, end, {
            from: desk(agent),
            to: middle(to.map(desk)),
            tone: 'handoff',
            label: caption,
          });
          score.rest(agent, done, end);
        }
        t = end;
      } else {
        for (const [agent] of givers) score.rest(agent, done, t);
      }
      return;
    }

    if (kind === 'conflict') {
      const agents = [...new Set(group.flatMap((step) => step.agents))];
      const place = (agent: string): DebatePlace => ({
        kind: 'debate',
        seat: agents.indexOf(agent),
      });
      const walk = Math.max(
        ...agents.map((agent) =>
          layout.walkSeconds(desk(agent), at(placeSeat(layout, agent, place(agent)))),
        ),
      );
      for (const agent of agents)
        score.play(agent, t, t + walk, directive('HANDOFF', place(agent), { arriveBy: t + walk }));
      t += walk;
      for (const step of group) {
        const [a, b] = step.agents;
        for (const agent of step.agents)
          score.play(
            agent,
            t,
            t + BEATS.conflict,
            directive('HANDOFF', place(agent), { caption: step.caption }),
          );
        if (a !== undefined && b !== undefined)
          arrow(t, t + BEATS.conflict, {
            from: at(placeSeat(layout, a, place(a))),
            to: at(placeSeat(layout, b, place(b))),
            tone: 'conflict',
            label: step.caption,
          });
        t += BEATS.conflict;
      }
      // They stay at the table, done, while the RECONCILER rules; then they go back to their desks.
      const ruling = next?.[0]?.agents.includes('reconciler') === true;
      for (const agent of agents)
        score.rest(agent, ruling ? directive('DONE', place(agent)) : done, t);
      return;
    }

    if (kind === 'deliver') {
      const giver = first.agents[0] as string;
      const receiver = first.to as string;
      // Anyone still waiting at the debate table goes back to their desk now.
      for (const agent of cast)
        if (score.restingOf(agent).place.kind === 'debate') score.rest(agent, done, t);
      score.play(
        giver,
        t,
        t + BEATS.work,
        directive('WORKING', { kind: 'desk' }, { caption: first.caption }),
      );
      t += BEATS.work;
      const place: VisitPlace = { kind: 'visit', agentIds: [receiver] };
      const walk = layout.walkSeconds(desk(giver), at(placeSeat(layout, giver, place)));
      score.play(
        giver,
        t,
        t + walk,
        directive('HANDOFF', place, { caption: first.caption, carrying: true, arriveBy: t + walk }),
      );
      t += walk;
      for (const step of group) {
        score.play(
          giver,
          t,
          t + BEATS.deliver,
          directive('HANDOFF', place, { caption: step.caption }),
        );
        arrow(t, t + BEATS.deliver, {
          from: desk(giver),
          to: desk(receiver),
          tone: 'handoff',
          label: step.caption,
        });
        score.tray.push({ start: t, count: step.tray as number });
        t += BEATS.deliver;
      }
      score.rest(giver, done, t);
      return;
    }

    if (kind === 'tray') {
      for (const step of group) {
        score.tray.push({ start: t, count: step.tray as number });
        t += BEATS.tray;
      }
      return;
    }

    // A hand-off step: its agent carries the result to `to`, then the receiver takes over.
    for (const step of group) {
      const receiver = step.to as string;
      const place: VisitPlace = { kind: 'visit', agentIds: [receiver] };
      for (const giver of step.agents) {
        const walk = layout.walkSeconds(desk(giver), at(placeSeat(layout, giver, place)));
        const end = t + walk + BEATS.handover;
        score.play(
          giver,
          t,
          end,
          directive('HANDOFF', place, {
            caption: step.caption,
            carrying: true,
            arriveBy: t + walk,
          }),
        );
        arrow(t, end, {
          from: desk(giver),
          to: desk(receiver),
          tone: 'handoff',
          label: step.caption,
        });
        score.rest(giver, directive('DONE', place), end);
        t = end;
      }
    }
  });

  // Everyone cheers where they stand, then the show ends and they go back to the Break Area.
  for (const agent of cast)
    score.play(
      agent,
      t,
      t + BEATS.cheer,
      directive('DONE', score.restingOf(agent).place, { cheer: true }),
    );
  t += BEATS.cheer;
  score.finish(t);
  return { duration: t, cues: score.cues, arrows: score.arrows, tray: score.tray };
}

/** What the show looks like `t` seconds in. */
export function frameAt(timeline: Timeline, t: number): Frame {
  const directives = new Map<string, Directive>();
  const ended = t >= timeline.duration;
  if (!ended) {
    for (const [agent, cues] of timeline.cues) {
      // Every agent's cues run without a gap to the end of the show.
      const cue = cues.find((item) => item.start <= t && t < item.end) as Cue;
      directives.set(agent, cue.directive);
    }
  }
  const tray = timeline.tray.filter((entry) => entry.start <= t).at(-1);
  return {
    directives,
    arrows: ended
      ? []
      : timeline.arrows.filter((span) => span.start <= t && t < span.end).map((span) => span.arrow),
    trayCount: ended || timeline.tray.length === 0 ? null : (tray?.count ?? 0),
    ended,
  };
}

/** The next moment after `t` when the frame changes; Infinity when it never does again. */
export function nextChange(timeline: Timeline, t: number): number {
  const moments = [
    timeline.duration,
    ...[...timeline.cues.values()].flatMap((cues) => cues.flatMap((cue) => [cue.start, cue.end])),
    ...timeline.arrows.flatMap((span) => [span.start, span.end]),
    ...timeline.tray.map((entry) => entry.start),
  ].filter((moment) => moment > t);
  return moments.length === 0 ? Infinity : Math.min(...moments);
}

/** Every caption and arrow label a timeline can show, for the honesty tests (AC-F-1). */
export function shownTexts(timeline: Timeline): Set<string> {
  const texts = new Set<string>();
  for (const cues of timeline.cues.values())
    for (const cue of cues) if (cue.directive.caption !== null) texts.add(cue.directive.caption);
  for (const span of timeline.arrows) texts.add(span.arrow.label);
  return texts;
}
