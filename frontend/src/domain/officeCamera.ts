/**
 * The office camera (spec §9.8, D-F-5; the numbers are PROPOSED).
 *
 * An orthographic camera at 35° elevation. The yaw starts at 45° and turns in 90° steps. There
 * are three zoom stops, each with its own pixel size, so zooming in makes the pixels a little
 * larger and the world a little more detailed. The camera's target snaps to the pixel grid in the
 * camera's own plane, so the picture never shimmers when it moves.
 *
 * Pure numbers only: the world turns these into three.js objects.
 */

export type Vec3 = readonly [number, number, number];

export const ELEVATION_DEGREES = 35;
export const START_YAW_DEGREES = 45;
export const YAW_STEP_DEGREES = 90;
/** How far the camera stands from its target; orthographic, so it only has to clear the scene. */
export const CAMERA_DISTANCE = 60;

/** Each zoom stop: the scale over the fitted view, and the pixel size at device pixel ratio 1. */
export const ZOOM_STOPS = [
  { scale: 1, pixelSize: 3 },
  { scale: 1.5, pixelSize: 4 },
  { scale: 2.25, pixelSize: 5 },
] as const;

/** The default pass edge strengths of three's RenderPixelatedPass (§9.8). */
export const EDGE_STRENGTH = { normal: 0.3, depth: 0.4 } as const;

const RADIANS = Math.PI / 180;

/** The yaw after `quarterTurns` 90° steps from the start, in [0, 360). */
export function yawDegrees(quarterTurns: number): number {
  const degrees = START_YAW_DEGREES + YAW_STEP_DEGREES * quarterTurns;
  return ((degrees % 360) + 360) % 360;
}

/** The zoom stop index, kept within the stops. */
export function clampZoom(index: number): number {
  return Math.min(ZOOM_STOPS.length - 1, Math.max(0, Math.round(index)));
}

function stop(index: number) {
  return ZOOM_STOPS[clampZoom(index)] as (typeof ZOOM_STOPS)[number];
}

export function zoomScale(index: number): number {
  return stop(index).scale;
}

/** The pass's pixel size in device pixels: the stop's size, scaled by the device pixel ratio. */
export function pixelSize(index: number, devicePixelRatio: number): number {
  return Math.max(1, Math.round(stop(index).pixelSize * devicePixelRatio));
}

/** The size of one pixel cell in CSS pixels, whatever the device pixel ratio. */
export function cellCssPixels(index: number): number {
  return stop(index).pixelSize;
}

export interface Basis {
  /** Screen right. */
  right: Vec3;
  /** Screen up. */
  up: Vec3;
  /** From the target towards the camera. */
  back: Vec3;
}

/**
 * The camera's axes for a yaw and an elevation. At yaw 0 the camera stands on +z looking
 * towards -z; the yaw turns it anticlockwise seen from above.
 */
export function cameraBasis(yaw: number, elevation: number = ELEVATION_DEGREES): Basis {
  const y = yaw * RADIANS;
  const e = elevation * RADIANS;
  const back: Vec3 = [Math.cos(e) * Math.sin(y), Math.sin(e), Math.cos(e) * Math.cos(y)];
  const right: Vec3 = [Math.cos(y), 0, -Math.sin(y)];
  const up: Vec3 = [
    back[1] * right[2] - back[2] * right[1],
    back[2] * right[0] - back[0] * right[2],
    back[0] * right[1] - back[1] * right[0],
  ];
  return { right, up, back };
}

const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const scaled = (v: Vec3, k: number): Vec3 => [v[0] * k, v[1] * k, v[2] * k];
const sum = (...vectors: Vec3[]): Vec3 =>
  vectors.reduce<Vec3>(
    (total, v) => [total[0] + v[0], total[1] + v[1], total[2] + v[2]],
    [0, 0, 0],
  );

export function cameraPosition(target: Vec3, basis: Basis, distance = CAMERA_DISTANCE): Vec3 {
  return sum(target, scaled(basis.back, distance));
}

export interface Extent {
  width: number;
  height: number;
}

/**
 * How wide and tall a box of `width` × `depth` floor and `height` walls appears on screen, in
 * world units, under `basis`.
 */
export function projectedExtent(
  floor: { width: number; depth: number },
  height: number,
  basis: Basis,
): Extent {
  const corners: Vec3[] = [];
  for (const x of [0, floor.width])
    for (const y of [0, height]) for (const z of [0, floor.depth]) corners.push([x, y, z]);
  const across = corners.map((corner) => dot(corner, basis.right));
  const along = corners.map((corner) => dot(corner, basis.up));
  return {
    width: Math.max(...across) - Math.min(...across),
    height: Math.max(...along) - Math.min(...along),
  };
}

/** CSS pixels per world unit at the first zoom stop: the whole extent fits, with a margin. */
export function fitPixelsPerUnit(viewport: Extent, extent: Extent, margin = 1.06): number {
  if (viewport.width <= 0 || viewport.height <= 0) return 1;
  return Math.min(
    viewport.width / (extent.width * margin),
    viewport.height / (extent.height * margin),
  );
}

/**
 * The target, moved in the camera's plane to the nearest multiple of `cell` world units along
 * screen right and screen up. The distance along the view direction is kept.
 */
export function snapTarget(target: Vec3, basis: Basis, cell: number): Vec3 {
  if (!(cell > 0)) return target;
  const snap = (value: number) => Math.round(value / cell) * cell;
  return sum(
    scaled(basis.right, snap(dot(target, basis.right))),
    scaled(basis.up, snap(dot(target, basis.up))),
    scaled(basis.back, dot(target, basis.back)),
  );
}

/**
 * A drag of `dx`, `dy` CSS pixels, as a move of the target on the ground: the floor follows the
 * pointer.
 */
export function panTarget(
  target: Vec3,
  basis: Basis,
  dx: number,
  dy: number,
  pixelsPerUnit: number,
): Vec3 {
  const groundAway: Vec3 = [-basis.back[0], 0, -basis.back[2]];
  const length = Math.hypot(groundAway[0], groundAway[2]);
  const away = scaled(groundAway, 1 / length);
  const rise = dot(away, basis.up);
  return sum(
    target,
    scaled(basis.right, -dx / pixelsPerUnit),
    scaled(away, dy / pixelsPerUnit / rise),
  );
}

/** The target kept over the floor's rectangle, on the ground. */
export function clampTarget(target: Vec3, floor: { width: number; depth: number }): Vec3 {
  return [
    Math.min(floor.width, Math.max(0, target[0])),
    0,
    Math.min(floor.depth, Math.max(0, target[2])),
  ];
}
