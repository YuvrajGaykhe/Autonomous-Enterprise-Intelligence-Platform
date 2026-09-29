/**
 * Draws a list of parts as one instanced mesh per shape and finish (spec §9.8, §9.10): the whole
 * office is a handful of draw calls, whatever its number of parts.
 */

import { useLayoutEffect, useMemo, useRef } from 'react';
import { Color, type InstancedMesh } from 'three';

import type { Finish, Part, Shape } from './kit/parts';
import { geometryFor, materialFor } from './materials';

const colour = new Color();

function BatchMesh({
  shape,
  finish,
  parts,
  shadows,
}: {
  shape: Shape;
  finish: Finish;
  parts: readonly Part[];
  shadows: 'cast' | 'receive' | 'both' | 'none';
}) {
  const mesh = useRef<InstancedMesh>(null);
  useLayoutEffect(() => {
    const current = mesh.current;
    if (current === null) return;
    parts.forEach((item, index) => {
      current.setMatrixAt(index, item.matrix);
      current.setColorAt(index, colour.set(item.color));
    });
    current.count = parts.length;
    current.instanceMatrix.needsUpdate = true;
    if (current.instanceColor !== null) current.instanceColor.needsUpdate = true;
    current.computeBoundingSphere();
  }, [parts]);
  const lit = finish === 'toon';
  return (
    <instancedMesh
      ref={mesh}
      args={[geometryFor(shape), materialFor(finish), parts.length]}
      castShadow={lit && (shadows === 'cast' || shadows === 'both')}
      receiveShadow={lit && (shadows === 'receive' || shadows === 'both')}
    />
  );
}

export function Batch({
  parts,
  shadows = 'both',
}: {
  parts: readonly Part[];
  shadows?: 'cast' | 'receive' | 'both' | 'none';
}) {
  const groups = useMemo(() => {
    const byKey = new Map<string, { shape: Shape; finish: Finish; parts: Part[] }>();
    for (const item of parts) {
      const key = `${item.shape}:${item.finish}`;
      const group = byKey.get(key) ?? { shape: item.shape, finish: item.finish, parts: [] };
      group.parts.push(item);
      byKey.set(key, group);
    }
    return [...byKey.entries()];
  }, [parts]);
  return (
    <>
      {groups.map(([key, group]) => (
        // The count is part of the key: a new count needs a new instance buffer.
        <BatchMesh
          key={`${key}:${group.parts.length}`}
          shape={group.shape}
          finish={group.finish}
          parts={group.parts}
          shadows={shadows}
        />
      ))}
    </>
  );
}
