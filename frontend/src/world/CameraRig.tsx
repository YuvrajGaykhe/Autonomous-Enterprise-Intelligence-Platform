/**
 * The orthographic camera (spec §9.8): fitted to the office at the first zoom stop, turned in 90°
 * steps with a short ease (none under reduced motion or `still`), and snapped to the pixel grid in
 * its own plane when pixel art is on.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useLayoutEffect, useRef } from 'react';
import type { OrthographicCamera } from 'three';

import { FLOOR, WALL_HEIGHT } from '@/domain/floorPlan';
import {
  cameraBasis,
  cameraPosition,
  cellCssPixels,
  fitPixelsPerUnit,
  projectedExtent,
  snapTarget,
  yawDegrees,
  zoomScale,
} from '@/domain/officeCamera';
import { useCamera } from '@/state/camera';

/** How long a 90° turn takes, in seconds. */
const TURN_SECONDS = 0.28;

export function CameraRig({ pixel, animate }: { pixel: boolean; animate: boolean }) {
  const camera = useThree((state) => state.camera) as OrthographicCamera;
  const size = useThree((state) => state.size);
  const invalidate = useThree((state) => state.invalidate);
  const quarterTurns = useCamera((state) => state.quarterTurns);
  const zoomIndex = useCamera((state) => state.zoomIndex);
  const target = useCamera((state) => state.target);
  const setPixelsPerUnit = useCamera((state) => state.setPixelsPerUnit);
  /** The yaw on screen, which eases towards the chosen one. */
  const shown = useRef(yawDegrees(quarterTurns));
  const wanted = useRef(shown.current);

  const place = (yaw: number) => {
    const basis = cameraBasis(yaw);
    const extent = projectedExtent(FLOOR, WALL_HEIGHT.tall, cameraBasis(45));
    const pixelsPerUnit =
      fitPixelsPerUnit({ width: size.width, height: size.height }, extent) * zoomScale(zoomIndex);
    const focus = pixel
      ? snapTarget(target, basis, cellCssPixels(zoomIndex) / pixelsPerUnit)
      : target;
    const [x, y, z] = cameraPosition(focus, basis);
    camera.position.set(x, y, z);
    camera.up.set(0, 1, 0);
    camera.lookAt(focus[0], focus[1], focus[2]);
    camera.zoom = pixelsPerUnit;
    camera.near = 0.1;
    camera.far = 200;
    camera.updateProjectionMatrix();
    setPixelsPerUnit(pixelsPerUnit);
    invalidate();
  };

  useLayoutEffect(() => {
    // Turn the short way round to the new yaw.
    const next = yawDegrees(quarterTurns);
    const delta = ((next - (wanted.current % 360) + 540) % 360) - 180;
    wanted.current += delta;
    if (!animate) shown.current = wanted.current;
    place(shown.current);
    // `place` reads the current state; it is not a dependency of its own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quarterTurns, zoomIndex, target, size.width, size.height, pixel, animate]);

  useFrame((_, delta) => {
    if (shown.current === wanted.current) return;
    const step = (90 / TURN_SECONDS) * delta;
    const remaining = wanted.current - shown.current;
    shown.current =
      Math.abs(remaining) <= step ? wanted.current : shown.current + Math.sign(remaining) * step;
    place(shown.current);
  });

  return null;
}
