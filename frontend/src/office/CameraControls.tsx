/**
 * The office view's controls (spec §9.8): turn in 90° steps, three zoom stops, a drag to move
 * and a reset. The buttons are the accessible path; the keys and the pointer are shortcuts.
 */

import { LocateFixed, RotateCcw, RotateCw, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useRef, type PointerEvent, type WheelEvent } from 'react';

import { ZOOM_STOPS } from '@/domain/officeCamera';
import { useCamera } from '@/state/camera';
import { Button } from '@/ui/button';

/** How far an arrow key moves the view, in CSS pixels. */
export const KEY_PAN_PIXELS = 48;
/** How much wheel travel makes one zoom step. */
export const WHEEL_STEP = 80;

export const CONTROLS_HELP =
  'Q and E turn the view, plus and minus zoom, the arrow keys move it and 0 resets it. The staff directory lists every agent in the office.';

export function CameraControls() {
  const zoomIndex = useCamera((state) => state.zoomIndex);
  const turn = useCamera((state) => state.turn);
  const zoom = useCamera((state) => state.zoom);
  const reset = useCamera((state) => state.reset);
  return (
    <div
      role="toolbar"
      aria-label="View controls"
      className="absolute right-3 bottom-3 z-30 flex gap-0.5 rounded-xl border bg-card/95 p-1 shadow-md"
    >
      <Button variant="ghost" size="sm" aria-label="Turn left (Q)" onClick={() => turn(-1)}>
        <RotateCcw aria-hidden="true" />
      </Button>
      <Button variant="ghost" size="sm" aria-label="Turn right (E)" onClick={() => turn(1)}>
        <RotateCw aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Zoom out (minus)"
        disabled={zoomIndex === 0}
        onClick={() => zoom(-1)}
      >
        <ZoomOut aria-hidden="true" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        aria-label="Zoom in (plus)"
        disabled={zoomIndex === ZOOM_STOPS.length - 1}
        onClick={() => zoom(1)}
      >
        <ZoomIn aria-hidden="true" />
      </Button>
      <Button variant="ghost" size="sm" aria-label="Reset the view (0)" onClick={reset}>
        <LocateFixed aria-hidden="true" />
      </Button>
    </div>
  );
}

/** Where a key belongs to what has focus, not to the view: a field, or an open panel. */
const KEEPS_KEYS = 'input, textarea, select, [contenteditable="true"], [role="dialog"]';

/**
 * The keys (spec §9.8), anywhere on the office page except in a field or an open panel.
 */
export function useCameraKeys() {
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const active = document.activeElement;
      if (active instanceof Element && active.closest(KEEPS_KEYS) !== null) return;
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const { turn, zoom, panBy, reset } = useCamera.getState();
      const actions: Record<string, () => void> = {
        q: () => turn(-1),
        e: () => turn(1),
        '+': () => zoom(1),
        '=': () => zoom(1),
        '-': () => zoom(-1),
        _: () => zoom(-1),
        '0': reset,
        ArrowLeft: () => panBy(KEY_PAN_PIXELS, 0),
        ArrowRight: () => panBy(-KEY_PAN_PIXELS, 0),
        ArrowUp: () => panBy(0, KEY_PAN_PIXELS),
        ArrowDown: () => panBy(0, -KEY_PAN_PIXELS),
      };
      const action = actions[event.key.length === 1 ? event.key.toLowerCase() : event.key];
      if (action === undefined) return;
      event.preventDefault();
      action();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}

/** The drag and the wheel over the office's viewport. */
export function useViewportPointer() {
  const drag = useRef<{ x: number; y: number } | null>(null);
  const wheel = useRef(0);

  const onPointerDown = (event: PointerEvent<HTMLElement>) => {
    if (event.button === 0) drag.current = { x: event.clientX, y: event.clientY };
  };
  const onPointerMove = (event: PointerEvent<HTMLElement>) => {
    const from = drag.current;
    if (from === null || (event.buttons & 1) === 0) return;
    useCamera.getState().panBy(event.clientX - from.x, event.clientY - from.y);
    drag.current = { x: event.clientX, y: event.clientY };
  };
  const onPointerUp = () => {
    drag.current = null;
  };
  const onWheel = (event: WheelEvent<HTMLElement>) => {
    wheel.current += event.deltaY;
    if (Math.abs(wheel.current) < WHEEL_STEP) return;
    useCamera.getState().zoom(wheel.current < 0 ? 1 : -1);
    wheel.current = 0;
  };

  return { onPointerDown, onPointerMove, onPointerUp, onPointerLeave: onPointerUp, onWheel };
}
