/**
 * The in-world labels' positions (spec §9.3, §9.8). Tags, bubbles and room signs are ordinary DOM
 * in the page's own React tree, laid over the canvas; each frame the world projects every label's
 * anchor through the camera and moves its element there, nearer labels above farther ones. One
 * tree and one pass, rather than a React root per label.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, type ReactNode } from 'react';
import { Vector3 } from 'three';

export type Anchor = readonly [number, number, number];

export class LabelLayer {
  readonly anchors = new Map<string, Anchor>();
  readonly elements = new Map<string, HTMLElement>();
  private readonly shown = new Map<string, string>();
  private readonly binders = new Map<string, (element: HTMLElement | null) => void>();
  private readonly point = new Vector3();

  /** The ref callback for the element of label `id`, the same one on every render. */
  bind(id: string): (element: HTMLElement | null) => void {
    let binder = this.binders.get(id);
    if (binder === undefined) {
      binder = (element) => {
        if (element === null) {
          this.elements.delete(id);
          this.shown.delete(id);
        } else {
          this.elements.set(id, element);
        }
      };
      this.binders.set(id, binder);
    }
    return binder;
  }

  /** Move every bound element to its anchor, as `camera` sees it on a `width` × `height` canvas. */
  project(camera: Parameters<Vector3['project']>[0], width: number, height: number): void {
    for (const [id, element] of this.elements) {
      const anchor = this.anchors.get(id);
      if (anchor === undefined) continue;
      this.point.set(anchor[0], anchor[1], anchor[2]).project(camera);
      const x = Math.round(((this.point.x + 1) / 2) * width);
      const y = Math.round(((1 - this.point.y) / 2) * height);
      const depth = String(Math.round(1000 - this.point.z * 500));
      const key = `${x} ${y} ${depth}`;
      if (this.shown.get(id) === key) continue;
      this.shown.set(id, key);
      element.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      element.style.zIndex = depth;
      element.style.visibility = 'visible';
    }
  }
}

/** Inside the canvas: projects the labels after the camera has moved, every rendered frame. */
export function LabelProjector({ layer, version }: { layer: LabelLayer; version: string }) {
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => invalidate(), [version, invalidate]);
  useFrame(({ camera, size }) => {
    // The renderer refreshes the camera's matrices only when it draws, after this callback.
    camera.updateMatrixWorld();
    layer.project(camera, size.width, size.height);
  });
  return null;
}

/** Outside the canvas: one label, hidden until it has been placed. */
export function Label({
  layer,
  id,
  children,
}: {
  layer: LabelLayer;
  id: string;
  children: ReactNode;
}) {
  return (
    <div ref={layer.bind(id)} className="invisible absolute top-0 left-0" data-label={id}>
      <div className="-translate-x-1/2 -translate-y-1/2">{children}</div>
    </div>
  );
}
