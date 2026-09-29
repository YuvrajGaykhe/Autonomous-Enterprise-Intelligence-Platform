/**
 * Soft sky light and one warm key light from the north-west, casting hard-edged shadows that suit
 * the pixel look (spec §9.8).
 */

import { useLayoutEffect, useRef } from 'react';
import type { DirectionalLight } from 'three';

import { FLOOR } from '@/domain/floorPlan';

export function Lighting() {
  const key = useRef<DirectionalLight>(null);
  useLayoutEffect(() => {
    const light = key.current;
    if (light === null) return;
    light.target.position.set(FLOOR.width / 2, 0, FLOOR.depth / 2);
    light.target.updateMatrixWorld();
    const shadow = light.shadow.camera;
    shadow.left = -26;
    shadow.right = 26;
    shadow.top = 20;
    shadow.bottom = -20;
    shadow.near = 1;
    shadow.far = 90;
    shadow.updateProjectionMatrix();
  }, []);
  return (
    <>
      <hemisphereLight args={['#fff6e8', '#7a5c40', 1.5]} />
      <ambientLight intensity={0.35} />
      <directionalLight
        ref={key}
        position={[FLOOR.width / 2 - 14, 30, FLOOR.depth / 2 - 12]}
        intensity={2.1}
        color="#fff1dc"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0008}
        shadow-normalBias={0.02}
      />
    </>
  );
}
