/**
 * The neon arrows' geometry (spec §9.3, §9.5): an arc from the giver's desk to the taker's, rising
 * with its length, and the point over its top where its label floats.
 */

import type { Arrow } from '@/domain/director';

import type { Anchor } from '../LabelLayer';

/** The arc's ends stand this high; its top rises with its length, up to a limit. */
export const END_HEIGHT = 1.35;

/** A point `t` of the way along the arc, 0 at `from`, 1 at `to`. */
export function arcPoint(arrow: Arrow, t: number): [number, number, number] {
  const length = Math.hypot(arrow.to[0] - arrow.from[0], arrow.to[1] - arrow.from[1]);
  const rise = Math.min(2.4, 0.6 + length * 0.12);
  return [
    arrow.from[0] + (arrow.to[0] - arrow.from[0]) * t,
    END_HEIGHT + rise * 4 * t * (1 - t),
    arrow.from[1] + (arrow.to[1] - arrow.from[1]) * t,
  ];
}

/** Where the arrow's label floats: just over the top of its arc. */
export function arrowLabelAnchor(arrow: Arrow): Anchor {
  const [x, y, z] = arcPoint(arrow, 0.5);
  return [x, y + 0.35, z];
}
