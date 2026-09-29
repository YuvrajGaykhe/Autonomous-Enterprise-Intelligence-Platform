/**
 * The world's shared geometries and materials (spec §9.8): toon shading with a 3-step gradient,
 * unlit colour for anything that glows, and the back-face hull of the working glow.
 */

import {
  BackSide,
  BoxGeometry,
  ConeGeometry,
  CylinderGeometry,
  DataTexture,
  MeshBasicMaterial,
  MeshToonMaterial,
  NearestFilter,
  RedFormat,
  SphereGeometry,
  TorusGeometry,
  type BufferGeometry,
  type Material,
} from 'three';

import type { Finish, Shape } from './kit/parts';

function toonGradient(): DataTexture {
  const texture = new DataTexture(new Uint8Array([90, 175, 255]), 3, 1, RedFormat);
  texture.minFilter = NearestFilter;
  texture.magFilter = NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

let geometries: Record<Shape, BufferGeometry> | null = null;
let materials: Record<Finish, Material> | null = null;

export function geometryFor(shape: Shape): BufferGeometry {
  geometries ??= {
    box: new BoxGeometry(1, 1, 1),
    cylinder: new CylinderGeometry(0.5, 0.5, 1, 14),
    sphere: new SphereGeometry(0.5, 14, 10),
    cone: new ConeGeometry(0.5, 1, 10),
    torus: new TorusGeometry(0.5, 0.1, 6, 20),
  };
  return geometries[shape];
}

export function materialFor(finish: Finish): Material {
  materials ??= {
    toon: new MeshToonMaterial({ color: 0xffffff, gradientMap: toonGradient() }),
    glow: new MeshBasicMaterial({ color: 0xffffff }),
    outline: new MeshBasicMaterial({ color: 0xffffff, side: BackSide }),
  };
  return materials[finish];
}
