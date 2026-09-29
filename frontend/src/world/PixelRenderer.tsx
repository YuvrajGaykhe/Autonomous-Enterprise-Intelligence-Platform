/**
 * The pixel pass (spec §9.8, D-F-5): three's RenderPixelatedPass with its default edge strengths,
 * then the output pass for colour space. The pixel size follows the zoom stop and the device pixel
 * ratio. While it is mounted it renders every frame instead of R3F's default render; the Smooth
 * switch unmounts it.
 *
 * The shadow map is updated once per frame, before the beauty render, rather than again for the
 * normal render the pass also makes.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo } from 'react';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { RenderPixelatedPass } from 'three/examples/jsm/postprocessing/RenderPixelatedPass.js';

import { EDGE_STRENGTH, pixelSize } from '@/domain/officeCamera';

export function PixelRenderer({ zoomIndex }: { zoomIndex: number }) {
  const gl = useThree((state) => state.gl);
  const scene = useThree((state) => state.scene);
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const dpr = useThree((state) => state.viewport.dpr);

  const { composer, pass } = useMemo(() => {
    const effects = new EffectComposer(gl);
    const pixelated = new RenderPixelatedPass(pixelSize(0, dpr), scene, camera, {
      normalEdgeStrength: EDGE_STRENGTH.normal,
      depthEdgeStrength: EDGE_STRENGTH.depth,
    });
    effects.addPass(pixelated);
    effects.addPass(new OutputPass());
    return { composer: effects, pass: pixelated };
  }, [gl, scene, camera, dpr]);

  useEffect(() => {
    composer.setPixelRatio(dpr);
    composer.setSize(size.width, size.height);
  }, [composer, dpr, size.width, size.height]);

  useEffect(() => {
    pass.setPixelSize(pixelSize(zoomIndex, dpr));
  }, [pass, zoomIndex, dpr]);

  useEffect(() => {
    gl.shadowMap.autoUpdate = false;
    return () => {
      gl.shadowMap.autoUpdate = true;
      composer.dispose();
      pass.dispose();
    };
  }, [gl, composer, pass]);

  useFrame(() => {
    gl.shadowMap.needsUpdate = true;
    composer.render();
  }, 1);

  return null;
}
