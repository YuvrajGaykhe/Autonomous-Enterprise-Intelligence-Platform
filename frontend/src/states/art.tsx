/**
 * Pixel art for the empty states, the tour and the office's loading screen (F6). Every picture is
 * drawn here as rows of palette letters and rendered as crisp SVG rectangles: no image file, no
 * request. The pictures are decorative, so they are hidden from assistive technology; the words
 * beside them carry the meaning (§10).
 *
 * The outline letter `k` takes the text colour, so the art follows the light and dark schemes.
 */

import { cn } from '@/lib/utils';

const PALETTE: Readonly<Record<string, string>> = {
  k: 'currentColor',
  w: '#c8894f',
  W: '#8a5a33',
  c: '#f3e6c9',
  o: '#d9a86c',
  p: '#ffffff',
  g: '#a1a1aa',
  G: '#71717a',
  s: '#f1c27d',
  n: '#475569',
  b: '#22d3ee',
  r: '#dc2626',
  y: '#facc15',
  e: '#22c55e',
};

export const ART = {
  /** An office agent with its antenna bulb. */
  agent: [
    '.....bb.....',
    '.....kk.....',
    '...kkkkkk...',
    '..kssssssk..',
    '..kskssksk..',
    '..kssssssk..',
    '...kssssk...',
    '..knnnnnnk..',
    '.knnnnnnnnk.',
    '.knnnnnnnnk.',
    '.ksnnnnnnsk.',
    '..knnnnnnk..',
    '..kGGkkGGk..',
    '..kGk..kGk..',
    '..kkk..kkk..',
  ],
  /** An empty in-tray. */
  tray: [
    '..kkkkkkkkkkkk..',
    '.kcccccccccccck.',
    '.kcccccccccccck.',
    'kkkkkkkkkkkkkkkk',
    'kwwwwwwwwwwwwwwk',
    'kwwwwkkkkkkwwwwk',
    'kwwwwwwwwwwwwwwk',
    'kWWWWWWWWWWWWWWk',
    'kkkkkkkkkkkkkkkk',
  ],
  /** A corkboard with pins and no notes. */
  corkboard: [
    'kkkkkkkkkkkkkkkk',
    'kWWWWWWWWWWWWWWk',
    'kWooooooooooooWk',
    'kWorooooooooooWk',
    'kWooooooooooooWk',
    'kWooooooooyoooWk',
    'kWooooooooooooWk',
    'kWoooboooooooeWk',
    'kWooooooooooooWk',
    'kWWWWWWWWWWWWWWk',
    'kkkkkkkkkkkkkkkk',
  ],
  /** A filing cabinet with an open, empty drawer. */
  cabinet: [
    '..kkkkkkkkkkkk..',
    '..kggggggggggk..',
    '..kgkkkkkkkkgk..',
    '..kgk......kgk..',
    '..kgkkkkkkkkgk..',
    '..kggggggggggk..',
    '..kgggkkkkgggk..',
    '..kggggggggggk..',
    '..kggggggggggk..',
    '..kgggkkkkgggk..',
    '..kggggggggggk..',
    '..kkkkkkkkkkkk..',
  ],
  /** A desk with a monitor. */
  desk: [
    '...kkkkkkkkkk...',
    '...kbbbbbbbbk...',
    '...kbkkkbbbbk...',
    '...kbbbbbbbbk...',
    '...kbkkkkkbbk...',
    '...kbbbbbbbbk...',
    '...kkkkkkkkkk...',
    '.......kk.......',
    '..kkkkkkkkkkkk..',
    'kkkkkkkkkkkkkkkk',
    'kwwwwwwwwwwwwwwk',
    'kWWWWWWWWWWWWWWk',
    'kkkkkkkkkkkkkkkk',
    '.kWk........kWk.',
    '.kWk........kWk.',
    '.kkk........kkk.',
  ],
  /** A rubber stamp over a stamped sheet. */
  stamp: [
    '......kkkk......',
    '.....krrrrk.....',
    '.....krrrrk.....',
    '......krrk......',
    '......krrk......',
    '....kkkkkkkk....',
    '...kWWWWWWWWk...',
    '...kkkkkkkkkk...',
    '................',
    'kkkkkkkkkkkkkkkk',
    'kppppppppppppppk',
    'kpprrrrrrrrrrppk',
    'kpprprrrrrrprppk',
    'kpprrrrrrrrrrppk',
    'kppppppppppppppk',
    'kkkkkkkkkkkkkkkk',
  ],
} as const satisfies Record<string, readonly string[]>;

export type ArtName = keyof typeof ART;

export interface Run {
  x: number;
  y: number;
  width: number;
  fill: string;
}

/** A picture as runs of one colour along each row, so each run is one rectangle. */
export function runsOf(rows: readonly string[]): Run[] {
  const runs: Run[] = [];
  rows.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      const letter = row.charAt(x);
      let end = x + 1;
      while (end < row.length && row.charAt(end) === letter) end += 1;
      const fill = PALETTE[letter];
      if (fill !== undefined) runs.push({ x, y, width: end - x, fill });
      x = end;
    }
  });
  return runs;
}

export function PixelArt({ name, className }: { name: ArtName; className?: string }) {
  const rows = ART[name];
  const width = rows[0]?.length ?? 0;
  return (
    <svg
      aria-hidden="true"
      data-art={name}
      viewBox={`0 0 ${width} ${rows.length}`}
      shapeRendering="crispEdges"
      className={cn('h-16 w-auto', className)}
    >
      {runsOf(rows).map((run) => (
        <rect
          key={`${run.x}-${run.y}`}
          x={run.x}
          y={run.y}
          width={run.width}
          height={1}
          fill={run.fill}
        />
      ))}
    </svg>
  );
}
