/**
 * The agents' bodies (spec §9.9): procedural, about 2.5 heads tall, each role with its own
 * silhouette and prop. Looks (skin and hair) come from a hash of the agent's id, so they never
 * change between visits (§9.7). The CEO has no body: the CEO is the user, and the chair stays
 * empty.
 *
 * Every body is built facing +z with its feet at y = 0, standing or sitting, then placed at its
 * seat. The antenna bulb is returned apart from the body, because its colour follows the state.
 */

import type { Pose, Seat } from '@/domain/floorPlan';
import type { AgentKind } from '@/domain/roster';
import { hashString, pick } from '@/domain/seed';

import { box, glowBox, part, placed, type Part, type Triple } from './parts';

const SKIN = ['#f2c9a0', '#e0ac7e', '#c68b5e', '#8d5a3b', '#f5d6b8'] as const;
const HAIR = ['#2d2019', '#5a3a22', '#a3642f', '#d8b25a', '#1f1f24', '#7a2f2f'] as const;
const EYES = '#23232b';

/** Each role's clothes (PROPOSED role colours, §9.3). */
const OUTFIT: Readonly<
  Record<Exclude<AgentKind, 'ceo' | 'memory'>, { shirt: string; legs: string }>
> = {
  connector: { shirt: '#e8742c', legs: '#3b4a63' },
  linker: { shirt: '#2a9d8f', legs: '#34495e' },
  signals: { shirt: '#7c5cbf', legs: '#3b3f4f' },
  sales: { shirt: '#23395d', legs: '#23395d' },
  support: { shirt: '#2f9e6e', legs: '#3b4252' },
  reconciler: { shirt: '#22222a', legs: '#22222a' },
  briefWriter: { shirt: '#8e3b46', legs: '#3b3f4f' },
};

interface Frame {
  /** The height of the hips, the torso's centre and the head's centre. */
  hips: number;
  torso: number;
  head: number;
}

const FRAMES: Readonly<Record<Pose, Frame>> = {
  stand: { hips: 0.4, torso: 0.62, head: 1.05 },
  sit: { hips: 0.5, torso: 0.72, head: 1.15 },
};

const HEAD = { width: 0.46, height: 0.42, depth: 0.42 } as const;

function legs(pose: Pose, colour: string, shoes: string): Part[] {
  if (pose === 'stand') {
    return [-0.11, 0.11].flatMap((x) => [
      box(colour, [0.16, 0.36, 0.18], [x, 0.22, 0]),
      box(shoes, [0.17, 0.08, 0.24], [x, 0.04, 0.03]),
    ]);
  }
  return [-0.11, 0.11].flatMap((x) => [
    box(colour, [0.16, 0.16, 0.4], [x, 0.5, 0.16]),
    box(colour, [0.16, 0.42, 0.16], [x, 0.27, 0.34]),
    box(shoes, [0.17, 0.08, 0.24], [x, 0.04, 0.38]),
  ]);
}

/** Arms at the sides when standing; reaching forward to a desk when sitting. */
function arms(pose: Pose, frame: Frame, sleeve: string, skin: string): Part[] {
  const shoulder = frame.torso + 0.18;
  return [-0.29, 0.29].flatMap((x) => {
    if (pose === 'stand') {
      return [
        box(sleeve, [0.12, 0.38, 0.14], [x, shoulder - 0.19, 0]),
        part('sphere', skin, [0.12, 0.12, 0.12], [x, shoulder - 0.42, 0]),
      ];
    }
    return [
      box(sleeve, [0.12, 0.36, 0.14], [x, shoulder - 0.04, 0.18], [-1.35, 0, 0]),
      part('sphere', skin, [0.12, 0.12, 0.12], [x * 0.9, shoulder - 0.09, 0.4]),
    ];
  });
}

function head(frame: Frame, skin: string, hair: string | null): Part[] {
  const top = frame.head + HEAD.height / 2;
  const parts = [
    box(skin, [HEAD.width, HEAD.height, HEAD.depth], [0, frame.head, 0]),
    box(EYES, [0.07, 0.09, 0.02], [-0.1, frame.head + 0.01, HEAD.depth / 2 + 0.005]),
    box(EYES, [0.07, 0.09, 0.02], [0.1, frame.head + 0.01, HEAD.depth / 2 + 0.005]),
    box('#e89a8a', [0.06, 0.03, 0.02], [-0.16, frame.head - 0.08, HEAD.depth / 2 + 0.004]),
    box('#e89a8a', [0.06, 0.03, 0.02], [0.16, frame.head - 0.08, HEAD.depth / 2 + 0.004]),
  ];
  if (hair !== null) {
    parts.push(
      box(hair, [HEAD.width + 0.04, 0.12, HEAD.depth + 0.04], [0, top + 0.02, 0]),
      box(hair, [HEAD.width + 0.04, 0.3, 0.1], [0, frame.head + 0.06, -HEAD.depth / 2 - 0.02]),
    );
  }
  return parts;
}

/** The antenna's stalk; its tip is the bulb (§9.3). */
function antenna(frame: Frame, extra = 0): Part[] {
  const top = frame.head + HEAD.height / 2 + 0.08 + extra;
  return [part('cylinder', '#4a4f57', [0.03, 0.24, 0.03], [0, top + 0.12, 0])];
}

/** Where the bulb sits on a body of this pose, in the body's frame. */
export function bulbHeight(kind: AgentKind, pose: Pose): number {
  const frame = FRAMES[pose];
  return frame.head + HEAD.height / 2 + 0.08 + (kind === 'memory' ? 0.12 : 0) + 0.3;
}

function role(kind: AgentKind, frame: Frame, skin: string): Part[] {
  const top = frame.head + HEAD.height / 2;
  const chest = frame.torso;
  switch (kind) {
    case 'connector':
      return [
        part('cylinder', '#f2c230', [0.5, 0.16, 0.48], [0, top + 0.06, 0]),
        box('#e0b020', [0.6, 0.03, 0.58], [0, top - 0.01, 0.03]),
        box('#d8dde3', [0.46, 0.05, 0.29], [0, chest + 0.02, 0]),
      ];
    case 'linker':
      return [
        part('torus', '#c8a24a', [0.2, 0.2, 0.2], [0.34, frame.torso - 0.05, 0.2]),
        glowBox('#d7eef7', [0.13, 0.13, 0.01], [0.34, frame.torso - 0.05, 0.2]),
        box(skin, [0.04, 0.14, 0.04], [0.34, frame.torso - 0.2, 0.2]),
      ];
    case 'signals':
      return [
        box('#1f1f24', [0.16, 0.06, 0.02], [-0.1, frame.head + 0.02, HEAD.depth / 2 + 0.02]),
        box('#1f1f24', [0.16, 0.06, 0.02], [0.1, frame.head + 0.02, HEAD.depth / 2 + 0.02]),
      ];
    case 'sales':
      return [
        box('#f5f5f0', [0.14, 0.4, 0.02], [0, chest + 0.02, 0.145]),
        box('#c0392b', [0.06, 0.3, 0.02], [0, chest, 0.155]),
      ];
    case 'support':
      return [
        part(
          'torus',
          '#2b2b30',
          [0.58, 0.58, 0.58],
          [0, frame.head + 0.02, 0],
          [0, Math.PI / 2, 0],
        ),
        box('#2b2b30', [0.06, 0.16, 0.14], [-0.25, frame.head, 0]),
        box('#2b2b30', [0.06, 0.16, 0.14], [0.25, frame.head, 0]),
        box('#2b2b30', [0.03, 0.03, 0.2], [-0.2, frame.head - 0.12, 0.14]),
      ];
    case 'reconciler':
      return [
        box('#f2efe6', [0.2, 0.36, 0.44], [-0.28, frame.head - 0.05, -0.02]),
        box('#f2efe6', [0.2, 0.36, 0.44], [0.28, frame.head - 0.05, -0.02]),
        box('#f2efe6', [0.52, 0.12, 0.48], [0, top + 0.03, 0]),
        box('#f5f5f0', [0.24, 0.1, 0.02], [0, chest + 0.16, 0.145]),
        part(
          'cylinder',
          '#7a4a26',
          [0.08, 0.2, 0.08],
          [0.36, frame.torso + 0.02, 0.26],
          [0, 0, Math.PI / 2],
        ),
        part('cylinder', '#5a3a1e', [0.03, 0.26, 0.03], [0.36, frame.torso - 0.1, 0.26]),
      ];
    case 'briefWriter':
      return [box('#f0e6c8', [0.04, 0.2, 0.04], [0.25, frame.head + 0.1, 0.05], [0.3, 0, 0.4])];
    case 'memory':
    case 'ceo':
      return [];
  }
}

/** MEMORY: a friendly robot, the Layer 1 store (§9.9). */
function robot(frame: Frame): Part[] {
  const steel = '#9aa7b4';
  const dark = '#5b6570';
  return [
    box(dark, [0.18, 0.3, 0.2], [-0.14, 0.15, 0]),
    box(dark, [0.18, 0.3, 0.2], [0.14, 0.15, 0]),
    box(steel, [0.66, 0.66, 0.48], [0, 0.62, 0]),
    glowBox('#58d68d', [0.08, 0.06, 0.02], [-0.16, 0.72, 0.25]),
    glowBox('#f5b041', [0.08, 0.06, 0.02], [0, 0.72, 0.25]),
    glowBox('#5dade2', [0.08, 0.06, 0.02], [0.16, 0.72, 0.25]),
    box(dark, [0.34, 0.2, 0.02], [0, 0.52, 0.25]),
    part('cylinder', dark, [0.1, 0.46, 0.1], [-0.4, 0.62, 0]),
    part('cylinder', dark, [0.1, 0.46, 0.1], [0.4, 0.62, 0]),
    part('sphere', steel, [0.16, 0.16, 0.16], [-0.4, 0.36, 0]),
    part('sphere', steel, [0.16, 0.16, 0.16], [0.4, 0.36, 0]),
    box(steel, [0.54, 0.42, 0.46], [0, frame.head + 0.1, 0]),
    glowBox('#5de0f0', [0.42, 0.1, 0.02], [0, frame.head + 0.12, 0.235]),
    box(dark, [0.08, 0.14, 0.14], [-0.3, frame.head + 0.1, 0]),
    box(dark, [0.08, 0.14, 0.14], [0.3, frame.head + 0.1, 0]),
  ];
}

export interface Body {
  parts: Part[];
  /** Where the antenna bulb goes, in world units. */
  bulb: Triple;
}

/** An agent's body at its seat. The CEO has none. */
export function bodyFor(agentId: string, kind: AgentKind, seat: Seat): Body | null {
  if (kind === 'ceo') return null;
  const seed = hashString(agentId);
  const frame = FRAMES[seat.pose];
  let local: Part[];
  if (kind === 'memory') {
    local = [...robot(frame), ...antenna(frame, 0.12)];
  } else {
    const skin = pick(SKIN, seed);
    const outfit = OUTFIT[kind];
    const hair = kind === 'connector' || kind === 'reconciler' ? null : pick(HAIR, seed >>> 3);
    local = [
      ...legs(seat.pose, outfit.legs, '#2b2b30'),
      box(outfit.shirt, [0.44, 0.44, 0.28], [0, frame.torso, 0]),
      ...arms(seat.pose, frame, outfit.shirt, skin),
      ...head(frame, skin, hair),
      ...role(kind, frame, skin),
      ...antenna(frame),
    ];
  }
  return {
    parts: placed(local, seat.x, 0, seat.z, seat.facing),
    // The bulb sits on the head's centre line, so turning the body leaves it in place.
    bulb: [seat.x, bulbHeight(kind, seat.pose), seat.z],
  };
}
