/**
 * The furniture (spec §9.8, PROPOSED): each kind built from primitive parts in its own frame, its
 * front towards +z, then placed where the floor plan puts it.
 *
 * The models are procedural rather than downloaded CC0 files, so the world ships no asset files
 * and no third-party models (recorded in the F3 phase record). Nothing here shows data: the only
 * screens that carry content are SIGNALS_AGENT's board and the CEO's tray and corkboard, which are
 * drawn from API data elsewhere. Every other monitor is blank.
 */

import type { FurnitureItem, FurnitureKind } from '@/domain/floorPlan';

import { box, glowBox, part, placed, type Part } from './parts';

const WOOD = { light: '#b07a45', mid: '#9c6b3f', dark: '#6e4a2b', deep: '#4f3420' } as const;
const METAL = { light: '#a9b1bb', mid: '#8a939e', dark: '#3d434c', black: '#22252b' } as const;

function desk(): Part[] {
  return [
    box(WOOD.mid, [1.3, 0.06, 0.62], [0, 0.72, 0]),
    box(WOOD.dark, [0.06, 0.69, 0.56], [-0.6, 0.345, 0]),
    box(WOOD.dark, [0.06, 0.69, 0.56], [0.6, 0.345, 0]),
    box(WOOD.dark, [1.14, 0.4, 0.04], [0, 0.48, 0.26]),
    box('#e9e4d8', [0.36, 0.02, 0.14], [-0.15, 0.76, -0.12]),
  ];
}

function chair(): Part[] {
  return [
    box('#3a3f4a', [0.46, 0.07, 0.44], [0, 0.44, 0]),
    box('#3a3f4a', [0.44, 0.48, 0.07], [0, 0.72, -0.2]),
    part('cylinder', METAL.dark, [0.06, 0.38, 0.06], [0, 0.22, 0]),
    part('cylinder', METAL.dark, [0.44, 0.04, 0.44], [0, 0.03, 0]),
  ];
}

function monitor(): Part[] {
  return [
    box(METAL.black, [0.56, 0.36, 0.05], [0, 1.02, 0]),
    glowBox('#20364f', [0.5, 0.3, 0.01], [0, 1.02, 0.03]),
    part('cylinder', METAL.dark, [0.05, 0.2, 0.05], [0, 0.84, -0.01]),
    box(METAL.dark, [0.2, 0.02, 0.14], [0, 0.76, 0]),
  ];
}

function serverRack(): Part[] {
  const parts = [box('#2f343c', [1.1, 1.9, 0.7], [0, 0.95, 0])];
  for (let row = 0; row < 6; row += 1) {
    parts.push(box('#1d2127', [0.96, 0.2, 0.02], [0, 0.35 + row * 0.26, 0.36]));
    parts.push(
      glowBox(
        row % 3 === 0 ? '#f5b041' : '#58d68d',
        [0.06, 0.05, 0.02],
        [0.36, 0.35 + row * 0.26, 0.37],
      ),
    );
    parts.push(glowBox('#58d68d', [0.06, 0.05, 0.02], [0.26, 0.35 + row * 0.26, 0.37]));
  }
  return parts;
}

function crateStack(): Part[] {
  return [
    box('#b07a3c', [0.5, 0.46, 0.5], [0, 0.23, 0]),
    box('#8d5e2c', [0.52, 0.06, 0.52], [0, 0.23, 0]),
    box('#c28a48', [0.4, 0.36, 0.4], [0.02, 0.64, 0], [0, 0.35, 0]),
  ];
}

function pallet(): Part[] {
  return [
    box('#a57842', [1.2, 0.12, 0.95], [0, 0.06, 0]),
    box('#b07a3c', [0.5, 0.5, 0.45], [-0.3, 0.37, -0.2]),
    box('#c28a48', [0.5, 0.42, 0.42], [0.3, 0.33, 0.18], [0, 0.2, 0]),
    box('#9a6a34', [0.44, 0.4, 0.4], [-0.25, 0.82, -0.18], [0, -0.3, 0]),
  ];
}

const BOOKS = ['#b8423a', '#3e6fb0', '#e0b43a', '#4f9a5b', '#7d4fa6', '#d9d2c3'] as const;

function bookshelf(): Part[] {
  const parts = [
    box(WOOD.dark, [1.25, 1.8, 0.06], [0, 0.9, -0.17]),
    box(WOOD.mid, [0.06, 1.8, 0.4], [-0.6, 0.9, 0]),
    box(WOOD.mid, [0.06, 1.8, 0.4], [0.6, 0.9, 0]),
  ];
  for (let shelf = 0; shelf < 4; shelf += 1) {
    parts.push(box(WOOD.mid, [1.2, 0.05, 0.4], [0, 0.05 + shelf * 0.55, 0]));
    if (shelf === 3) continue;
    for (let book = 0; book < 6; book += 1) {
      const height = 0.3 + ((book * 7 + shelf * 3) % 5) * 0.03;
      parts.push(
        box(
          BOOKS[(book + shelf * 2) % BOOKS.length] as string,
          [0.13, height, 0.3],
          [-0.42 + book * 0.16, 0.08 + shelf * 0.55 + height / 2, 0.02],
        ),
      );
    }
  }
  return parts;
}

function filingCabinet(): Part[] {
  const parts = [box(METAL.mid, [0.55, 1.1, 0.6], [0, 0.55, 0])];
  for (let drawer = 0; drawer < 3; drawer += 1) {
    parts.push(box(METAL.light, [0.48, 0.3, 0.02], [0, 0.22 + drawer * 0.35, 0.305]));
    parts.push(box(METAL.dark, [0.16, 0.04, 0.03], [0, 0.3 + drawer * 0.35, 0.32]));
  }
  return parts;
}

function plant(): Part[] {
  return [
    part('cylinder', '#c0643d', [0.4, 0.36, 0.4], [0, 0.18, 0]),
    part('sphere', '#3f9a4a', [0.55, 0.5, 0.55], [0, 0.6, 0]),
    part('sphere', '#57b95f', [0.4, 0.42, 0.4], [0.12, 0.85, 0.05]),
    part('sphere', '#2f7f3a', [0.34, 0.34, 0.34], [-0.14, 0.8, -0.08]),
  ];
}

function roundTable(): Part[] {
  return [
    part('cylinder', WOOD.mid, [1.9, 0.07, 1.9], [0, 0.72, 0]),
    part('cylinder', WOOD.dark, [0.2, 0.68, 0.2], [0, 0.35, 0]),
    part('cylinder', WOOD.dark, [0.9, 0.05, 0.9], [0, 0.03, 0]),
    box('#f2efe6', [0.34, 0.01, 0.44], [-0.3, 0.76, 0.1], [0, 0.3, 0]),
    box('#f2efe6', [0.34, 0.01, 0.44], [0.35, 0.76, -0.05], [0, -0.2, 0]),
  ];
}

function sofa(): Part[] {
  return [
    box('#c85a5a', [2.1, 0.4, 0.85], [0, 0.22, 0]),
    box('#b24c4c', [2.1, 0.55, 0.22], [0, 0.62, -0.32]),
    box('#b24c4c', [0.22, 0.55, 0.85], [-0.95, 0.42, 0]),
    box('#b24c4c', [0.22, 0.55, 0.85], [0.95, 0.42, 0]),
    box('#d86b6b', [0.8, 0.12, 0.6], [-0.42, 0.47, 0.06]),
    box('#d86b6b', [0.8, 0.12, 0.6], [0.42, 0.47, 0.06]),
  ];
}

function coffeeTable(): Part[] {
  return [
    box(WOOD.light, [1.1, 0.06, 0.6], [0, 0.4, 0]),
    box(WOOD.dark, [0.06, 0.38, 0.5], [-0.48, 0.19, 0]),
    box(WOOD.dark, [0.06, 0.38, 0.5], [0.48, 0.19, 0]),
    part('cylinder', '#f2efe6', [0.1, 0.12, 0.1], [-0.2, 0.49, 0.05]),
    part('cylinder', '#3e6fb0', [0.1, 0.12, 0.1], [0.25, 0.49, -0.08]),
  ];
}

function coffeeMachine(): Part[] {
  return [
    box('#b8a58a', [1.2, 0.9, 0.55], [0, 0.45, 0]),
    box('#d9cbb2', [1.24, 0.05, 0.6], [0, 0.92, 0]),
    box('#2b2b2e', [0.36, 0.46, 0.32], [-0.25, 1.17, -0.04]),
    glowBox('#e74c3c', [0.05, 0.05, 0.02], [-0.15, 1.3, 0.13]),
    part('cylinder', '#f2efe6', [0.1, 0.12, 0.1], [0.2, 1.0, 0.05]),
  ];
}

function waterCooler(): Part[] {
  return [
    box('#e8e8e8', [0.4, 0.95, 0.4], [0, 0.475, 0]),
    part('cylinder', '#9fd3f5', [0.3, 0.45, 0.3], [0, 1.18, 0]),
    box('#3e6fb0', [0.06, 0.06, 0.04], [0, 0.75, 0.21]),
  ];
}

function vendingMachine(): Part[] {
  const parts = [
    box('#c0392b', [0.95, 1.85, 0.7], [0, 0.925, 0]),
    glowBox('#fbe9d0', [0.6, 1.1, 0.02], [-0.1, 1.15, 0.36]),
    box(METAL.dark, [0.18, 0.5, 0.03], [0.34, 1.1, 0.36]),
  ];
  for (let row = 0; row < 4; row += 1)
    for (let column = 0; column < 3; column += 1)
      parts.push(
        box(
          BOOKS[(row + column) % BOOKS.length] as string,
          [0.12, 0.16, 0.02],
          [-0.3 + column * 0.2, 0.75 + row * 0.26, 0.375],
        ),
      );
  return parts;
}

function executiveDesk(): Part[] {
  return [
    box(WOOD.deep, [2.1, 0.08, 0.95], [0, 0.76, 0]),
    box(WOOD.dark, [2.0, 0.72, 0.06], [0, 0.36, 0.42]),
    box(WOOD.dark, [0.08, 0.72, 0.9], [-0.98, 0.36, 0]),
    box(WOOD.dark, [0.08, 0.72, 0.9], [0.98, 0.36, 0]),
    // The inbox tray; its paper is drawn from the inbox (§9.5 step 8).
    box('#c9b28a', [0.46, 0.05, 0.34], [0.62, 0.825, 0.05]),
    box(METAL.dark, [0.05, 0.3, 0.05], [-0.75, 0.95, -0.2]),
    part('cone', '#2f6b4f', [0.26, 0.16, 0.26], [-0.75, 1.13, -0.2]),
    box('#d4a24c', [0.36, 0.08, 0.04], [-0.1, 0.84, 0.36]),
  ];
}

function executiveChair(): Part[] {
  return [
    box('#3b2a20', [0.62, 0.1, 0.58], [0, 0.48, 0]),
    box('#3b2a20', [0.62, 0.85, 0.1], [0, 0.95, -0.27]),
    box('#2e2019', [0.1, 0.25, 0.5], [-0.33, 0.62, 0]),
    box('#2e2019', [0.1, 0.25, 0.5], [0.33, 0.62, 0]),
    part('cylinder', METAL.dark, [0.08, 0.4, 0.08], [0, 0.23, 0]),
    part('cylinder', METAL.dark, [0.55, 0.04, 0.55], [0, 0.03, 0]),
  ];
}

function corkboard(): Part[] {
  return [
    box(WOOD.dark, [1.5, 1.0, 0.06], [0, 1.35, 0]),
    box('#c49a6c', [1.38, 0.88, 0.02], [0, 1.35, 0.035]),
    box(WOOD.dark, [0.06, 1.0, 0.06], [-0.6, 0.45, 0]),
    box(WOOD.dark, [0.06, 1.0, 0.06], [0.6, 0.45, 0]),
  ];
}

function rug(): Part[] {
  return [
    box('#d4a24c', [3.4, 0.012, 2.3], [0, 0.006, 0]),
    box('#8e2f3c', [3.1, 0.014, 2.0], [0, 0.008, 0]),
  ];
}

function typewriter(): Part[] {
  return [
    box('#2f3b4a', [0.42, 0.14, 0.32], [0, 0.82, 0]),
    part('cylinder', METAL.black, [0.06, 0.44, 0.06], [0, 0.93, -0.1], [0, 0, Math.PI / 2]),
    box('#fbfaf5', [0.28, 0.24, 0.01], [0, 1.03, -0.12], [-0.2, 0, 0]),
    box(METAL.light, [0.34, 0.03, 0.12], [0, 0.9, 0.1], [0.3, 0, 0]),
  ];
}

function abacus(): Part[] {
  const parts = [
    box(WOOD.dark, [0.42, 0.04, 0.06], [0, 0.77, 0]),
    box(WOOD.dark, [0.42, 0.04, 0.06], [0, 1.03, 0]),
    box(WOOD.dark, [0.04, 0.3, 0.06], [-0.19, 0.9, 0]),
    box(WOOD.dark, [0.04, 0.3, 0.06], [0.19, 0.9, 0]),
  ];
  for (let rod = 0; rod < 4; rod += 1)
    for (let bead = 0; bead < 3; bead += 1)
      parts.push(
        part(
          'sphere',
          BOOKS[(rod + bead) % BOOKS.length] as string,
          [0.06, 0.05, 0.06],
          [-0.12 + bead * 0.07 + (rod % 2) * 0.05, 0.83 + rod * 0.06, 0],
        ),
      );
  return parts;
}

function magnifierStand(): Part[] {
  return [
    part('cylinder', METAL.dark, [0.16, 0.03, 0.16], [0, 0.765, 0]),
    part('cylinder', METAL.dark, [0.03, 0.3, 0.03], [0, 0.92, 0]),
    part('torus', '#c8a24a', [0.22, 0.22, 0.22], [0, 1.12, 0.02]),
    glowBox('#d7eef7', [0.15, 0.15, 0.01], [0, 1.12, 0.02]),
  ];
}

function whiteboard(): Part[] {
  return [
    box(METAL.light, [1.7, 1.05, 0.06], [0, 1.35, 0]),
    box('#f7f7f2', [1.58, 0.93, 0.02], [0, 1.35, 0.035]),
    box(METAL.dark, [0.05, 0.85, 0.05], [-0.7, 0.42, 0]),
    box(METAL.dark, [0.05, 0.85, 0.05], [0.7, 0.42, 0]),
  ];
}

function coveredCrate(): Part[] {
  return [
    box('#8d8474', [1.0, 0.8, 0.8], [0, 0.4, 0]),
    box('#d9d4c7', [1.08, 0.12, 0.88], [0, 0.82, 0]),
    box('#d9d4c7', [1.08, 0.6, 0.04], [0, 0.55, 0.44]),
    part('sphere', '#d9d4c7', [0.5, 0.3, 0.4], [0.15, 0.92, -0.05]),
  ];
}

function lamp(): Part[] {
  return [
    part('cylinder', METAL.dark, [0.3, 0.04, 0.3], [0, 0.02, 0]),
    part('cylinder', METAL.dark, [0.04, 1.4, 0.04], [0, 0.72, 0]),
    part('cone', '#f2d27a', [0.42, 0.3, 0.42], [0, 1.5, 0]),
    part('sphere', '#fff4c9', [0.14, 0.14, 0.14], [0, 1.38, 0], [0, 0, 0], 'glow'),
  ];
}

const KINDS: Readonly<Record<Exclude<FurnitureKind, 'signalsBoard'>, () => Part[]>> = {
  desk,
  chair,
  monitor,
  serverRack,
  crateStack,
  pallet,
  bookshelf,
  filingCabinet,
  plant,
  roundTable,
  sofa,
  coffeeMachine,
  waterCooler,
  vendingMachine,
  coffeeTable,
  executiveDesk,
  executiveChair,
  corkboard,
  rug,
  typewriter,
  abacus,
  magnifierStand,
  whiteboard,
  coveredCrate,
  lamp,
};

/** One item's parts, in place. SIGNALS_AGENT's board is drawn by its own component. */
export function furnitureParts(item: FurnitureItem): Part[] {
  if (item.kind === 'signalsBoard') return [];
  return placed(KINDS[item.kind](), item.x, 0, item.z, item.rotation);
}
