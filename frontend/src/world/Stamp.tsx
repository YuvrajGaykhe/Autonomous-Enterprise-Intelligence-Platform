/**
 * The decision stamp (spec §9.5, the decision episode): after a 201 the stamp comes down on the
 * CEO's tray and leaves its mark, green for APPROVED and red for REJECTED; the corkboard's new note
 * comes from the chain itself (§8.6). Confetti flies only for an approval, and never under reduced
 * motion or `still`, where the mark simply appears.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef } from 'react';
import type { Group, Mesh, MeshBasicMaterial } from 'three';
import {
  Color,
  InstancedBufferAttribute,
  InstancedMesh,
  Matrix4,
  Quaternion,
  Vector3,
  Euler,
} from 'three';

import { FURNITURE } from '@/domain/floorPlan';
import { seededRandom } from '@/domain/seed';
import type { StampCue } from '@/office/worldTypes';

import { trayTop } from './kit/dynamic';
import { geometryFor, materialFor } from './materials';

export const STAMP_HEX: Readonly<Record<StampCue['decision'], string>> = {
  APPROVED: '#2e9e5b',
  REJECTED: '#c0392b',
};

/** The stamp's moments, in seconds after the decision. */
export const STAMP_TIMES = { down: 0.35, press: 0.9, up: 1.3, mark: 4, confetti: 3.4 } as const;

const DESK = FURNITURE.find((item) => item.kind === 'executiveDesk');
/** The tray's centre on the desk, in world units (the desk's own frame puts it at +0.62, +0.05). */
const TRAY = DESK === undefined ? new Vector3() : new Vector3(DESK.x + 0.62, 0, DESK.z + 0.05);
const PIECES = 90;
const CONFETTI = ['#f5b041', '#58d68d', '#5dade2', '#ec7063', '#af7ac5', '#f7dc6f'] as const;

// Scratch objects for the confetti, reused every frame.
const spot = new Vector3();
const spin = new Euler();
const turn = new Quaternion();
const matrix = new Matrix4();
const PIECE_SIZE = new Vector3(0.09, 0.02, 0.06);

interface Piece {
  velocity: Vector3;
  spin: Vector3;
  colour: Color;
}

export function Stamp({
  stamp,
  trayCount,
  animate,
}: {
  stamp: StampCue | null;
  trayCount: number | null;
  animate: boolean;
}) {
  const invalidate = useThree((state) => state.invalidate);
  const started = useRef<{ id: number; at: number } | null>(null);
  const block = useRef<Group>(null);
  const mark = useRef<Mesh>(null);

  const confetti = useMemo(() => {
    const mesh = new InstancedMesh(geometryFor('box'), materialFor('glow'), PIECES);
    mesh.instanceColor = new InstancedBufferAttribute(new Float32Array(PIECES * 3), 3);
    mesh.count = 0;
    mesh.frustumCulled = false;
    return mesh;
  }, []);
  useEffect(() => () => confetti.dispose(), [confetti]);

  const pieces = useMemo<Piece[]>(() => {
    const random = seededRandom(stamp?.id ?? 1);
    return Array.from({ length: PIECES }, (_, index) => {
      const angle = random() * Math.PI * 2;
      const speed = 1.2 + random() * 2.2;
      return {
        velocity: new Vector3(Math.cos(angle) * speed, 3 + random() * 3, Math.sin(angle) * speed),
        spin: new Vector3(random() * 9, random() * 9, random() * 9),
        colour: new Color(CONFETTI[index % CONFETTI.length]),
      };
    });
  }, [stamp?.id]);

  useEffect(() => {
    if (stamp === null) return;
    if (started.current?.id !== stamp.id) started.current = { id: stamp.id, at: performance.now() };
    invalidate();
  }, [stamp, invalidate]);

  useFrame(() => {
    const current = started.current;
    const top = trayTop(trayCount);
    const seconds = current === null ? Infinity : (performance.now() - current.at) / 1000;
    const active = stamp !== null && seconds < STAMP_TIMES.mark;
    if (block.current !== null) {
      let lift: number;
      if (!animate) lift = 0;
      else if (seconds < STAMP_TIMES.down) lift = 0.9 * (1 - seconds / STAMP_TIMES.down);
      else if (seconds < STAMP_TIMES.press) lift = 0;
      else
        lift =
          0.9 * Math.min(1, (seconds - STAMP_TIMES.press) / (STAMP_TIMES.up - STAMP_TIMES.press));
      block.current.visible = active && (!animate || seconds < STAMP_TIMES.up);
      block.current.position.set(TRAY.x, top + lift, TRAY.z);
    }
    if (mark.current !== null) {
      mark.current.visible = active && (!animate || seconds >= STAMP_TIMES.down);
      mark.current.position.set(TRAY.x, top + 0.002, TRAY.z);
      if (stamp !== null)
        (mark.current.material as MeshBasicMaterial).color.set(STAMP_HEX[stamp.decision]);
    }

    const flying =
      active &&
      animate &&
      stamp?.decision === 'APPROVED' &&
      seconds >= STAMP_TIMES.down &&
      seconds < STAMP_TIMES.confetti;
    if (flying) {
      const t = seconds - STAMP_TIMES.down;
      pieces.forEach((piece, index) => {
        spot.set(
          TRAY.x + piece.velocity.x * t,
          Math.max(0.02, top + 0.2 + piece.velocity.y * t - 4.9 * t * t),
          TRAY.z + piece.velocity.z * t,
        );
        turn.setFromEuler(spin.set(piece.spin.x * t, piece.spin.y * t, piece.spin.z * t));
        confetti.setMatrixAt(index, matrix.compose(spot, turn, PIECE_SIZE));
        confetti.setColorAt(index, piece.colour);
      });
      confetti.count = PIECES;
      confetti.instanceMatrix.needsUpdate = true;
      if (confetti.instanceColor !== null) confetti.instanceColor.needsUpdate = true;
    } else {
      confetti.count = 0;
    }
    // Keep drawing while the stamp lands, even when the world renders on demand.
    if (active) invalidate();
  });

  return (
    <>
      <group ref={block} visible={false}>
        <mesh
          geometry={geometryFor('box')}
          position={[0, 0.03, 0]}
          scale={[0.3, 0.06, 0.22]}
          castShadow
        >
          <meshToonMaterial color="#3b2a20" />
        </mesh>
        <mesh geometry={geometryFor('cylinder')} position={[0, 0.2, 0]} scale={[0.07, 0.28, 0.07]}>
          <meshToonMaterial color="#5a3a22" />
        </mesh>
        <mesh geometry={geometryFor('sphere')} position={[0, 0.38, 0]} scale={[0.16, 0.16, 0.16]}>
          <meshToonMaterial color="#c0392b" />
        </mesh>
      </group>
      <mesh ref={mark} visible={false} geometry={geometryFor('box')} scale={[0.26, 0.004, 0.16]}>
        <meshBasicMaterial color="#2e9e5b" />
      </mesh>
      <primitive object={confetti} />
    </>
  );
}
