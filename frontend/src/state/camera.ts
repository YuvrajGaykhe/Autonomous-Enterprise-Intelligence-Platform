/**
 * The office camera's state (spec §9.8), shared by the world and the HTML controls over it. The
 * numbers and the snapping live in `domain/officeCamera.ts`.
 */

import { create } from 'zustand';

import { FLOOR } from '@/domain/floorPlan';
import {
  cameraBasis,
  clampTarget,
  clampZoom,
  panTarget,
  yawDegrees,
  type Vec3,
} from '@/domain/officeCamera';

export const HOME_TARGET: Vec3 = [FLOOR.width / 2, 0, FLOOR.depth / 2];

export interface CameraState {
  /** 90° steps from the starting yaw. */
  quarterTurns: number;
  zoomIndex: number;
  /** What the camera looks at, on the ground, before snapping. */
  target: Vec3;
  /** CSS pixels per world unit, as the world last fitted the view; drags pan by it. */
  pixelsPerUnit: number;
  turn: (steps: number) => void;
  zoom: (steps: number) => void;
  /** Move the view by a drag of `dx`, `dy` CSS pixels: the floor follows the pointer. */
  panBy: (dx: number, dy: number) => void;
  setPixelsPerUnit: (pixelsPerUnit: number) => void;
  reset: () => void;
}

export const initialCamera = {
  quarterTurns: 0,
  zoomIndex: 0,
  target: HOME_TARGET,
  pixelsPerUnit: 1,
} satisfies Partial<CameraState>;

export const useCamera = create<CameraState>()((set) => ({
  ...initialCamera,
  turn: (steps) => set((state) => ({ quarterTurns: state.quarterTurns + steps })),
  zoom: (steps) => set((state) => ({ zoomIndex: clampZoom(state.zoomIndex + steps) })),
  panBy: (dx, dy) =>
    set((state) => ({
      target: clampTarget(
        panTarget(
          state.target,
          cameraBasis(yawDegrees(state.quarterTurns)),
          dx,
          dy,
          state.pixelsPerUnit,
        ),
        FLOOR,
      ),
    })),
  setPixelsPerUnit: (pixelsPerUnit) => set({ pixelsPerUnit }),
  reset: () =>
    set((state) => ({
      quarterTurns: initialCamera.quarterTurns,
      zoomIndex: initialCamera.zoomIndex,
      target: initialCamera.target,
      pixelsPerUnit: state.pixelsPerUnit,
    })),
}));
