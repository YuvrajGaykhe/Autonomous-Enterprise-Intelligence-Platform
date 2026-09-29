/**
 * SIGNALS_AGENT's board (spec §9.2): a screen on a stand in the Signals Desk, turned to face the
 * camera, drawing the selected customer's real signals and band from `GET /risk/assessments/{id}`.
 */

import { useThree } from '@react-three/fiber';
import { useEffect, useMemo } from 'react';
import { CanvasTexture, LinearFilter, NearestFilter, SRGBColorSpace } from 'three';

import type { RiskBand } from '@/api/schemas/briefPayloadV1';
import { FURNITURE } from '@/domain/floorPlan';
import { boardColumns } from '@/domain/monitor';
import type { BoardState } from '@/office/worldTypes';

import { Batch } from './Batch';
import { box, part } from './kit/parts';

const WIDTH = 512;
const HEIGHT = 320;
const FONT = '"JetBrains Mono", ui-monospace, monospace';

const BAND_HEX: Readonly<Record<RiskBand, string>> = {
  NONE: '#94a3b8',
  WATCH: '#facc15',
  ELEVATED: '#fb923c',
  CRITICAL: '#f87171',
};

const WORDS: Readonly<Record<Exclude<BoardState['kind'], 'ready'>, string>> = {
  loading: '…',
  empty: 'NO BRIEF',
  error: 'NO SIGNAL',
};

function draw(canvas: HTMLCanvasElement, state: BoardState): void {
  const context = canvas.getContext('2d');
  if (context === null) return;
  context.fillStyle = '#0b1a14';
  context.fillRect(0, 0, WIDTH, HEIGHT);
  context.strokeStyle = '#1f4d3a';
  context.lineWidth = 6;
  context.strokeRect(3, 3, WIDTH - 6, HEIGHT - 6);
  context.textBaseline = 'middle';
  if (state.kind !== 'ready') {
    context.fillStyle = '#7dffa8';
    context.font = `40px ${FONT}`;
    context.textAlign = 'center';
    context.fillText(WORDS[state.kind], WIDTH / 2, HEIGHT / 2);
    return;
  }
  const { board } = state;
  context.textAlign = 'left';
  context.fillStyle = '#5de0f0';
  context.font = `28px ${FONT}`;
  context.fillText(board.title, 22, 32);
  context.font = `22px ${FONT}`;
  boardColumns(board.cells).forEach((column, index) => {
    column.forEach((cell, row) => {
      const x = 22 + index * 250;
      const y = 72 + row * 29;
      context.fillStyle = '#f5b041';
      context.fillText(cell.id, x, y);
      context.fillStyle = '#7dffa8';
      context.fillText(cell.shown, x + 58, y);
    });
  });
  context.fillStyle = BAND_HEX[board.band];
  context.font = `26px ${FONT}`;
  context.fillText(board.footer, 22, HEIGHT - 28);
}

const SCREEN = { width: 2.5, height: 1.56, centre: 1.78 } as const;

const FRAME = [
  box('#1d2027', [SCREEN.width + 0.14, SCREEN.height + 0.14, 0.08], [0, SCREEN.centre, 0]),
  box('#2b2f37', [0.1, 1.0, 0.1], [-0.8, 0.5, -0.02]),
  box('#2b2f37', [0.1, 1.0, 0.1], [0.8, 0.5, -0.02]),
  part('cylinder', '#2b2f37', [0.5, 0.04, 0.5], [-0.8, 0.02, 0]),
  part('cylinder', '#2b2f37', [0.5, 0.04, 0.5], [0.8, 0.02, 0]),
];

export const BOARD_ITEM = FURNITURE.find((item) => item.kind === 'signalsBoard');

export function SignalsBoard({
  board,
  yaw,
  pixel,
}: {
  board: BoardState;
  yaw: number;
  pixel: boolean;
}) {
  const invalidate = useThree((state) => state.invalidate);
  const canvas = useMemo(() => {
    const element = document.createElement('canvas');
    element.width = WIDTH;
    element.height = HEIGHT;
    return element;
  }, []);
  const texture = useMemo(() => {
    const map = new CanvasTexture(canvas);
    map.colorSpace = SRGBColorSpace;
    map.generateMipmaps = false;
    return map;
  }, [canvas]);

  useEffect(() => {
    let live = true;
    const paint = () => {
      if (!live) return;
      draw(canvas, board);
      texture.needsUpdate = true;
      invalidate();
    };
    paint();
    // Draw again once the monospace face has loaded, if it had not yet.
    void document.fonts.load(`22px ${FONT}`).then(paint, () => undefined);
    return () => {
      live = false;
    };
  }, [board, canvas, texture, invalidate]);

  useEffect(() => {
    texture.magFilter = pixel ? NearestFilter : LinearFilter;
    texture.minFilter = pixel ? NearestFilter : LinearFilter;
    texture.needsUpdate = true;
    invalidate();
  }, [pixel, texture, invalidate]);

  useEffect(() => () => texture.dispose(), [texture]);

  if (BOARD_ITEM === undefined) return null;
  return (
    <group position={[BOARD_ITEM.x, 0, BOARD_ITEM.z]} rotation={[0, (yaw * Math.PI) / 180, 0]}>
      <Batch parts={FRAME} />
      <mesh position={[0, SCREEN.centre, 0.045]}>
        <planeGeometry args={[SCREEN.width, SCREEN.height]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
    </group>
  );
}
