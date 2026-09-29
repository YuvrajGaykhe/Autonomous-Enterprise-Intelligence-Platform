/**
 * SIGNALS_AGENT's board (spec §9.2: "its monitor shows the real signal values").
 *
 * The board shows the selected customer's assessment: its signals S1–S15 as the brief lists them,
 * and its band as the word. A value too long for the board is clipped with "…" on the board only;
 * the office's text mirror and the agent's panel always show it whole.
 */

import type { RiskBand } from '@/api/schemas/briefPayloadV1';

import type { SignalRow } from './briefView';

/** The characters a value may take on the board. */
export const BOARD_VALUE_WIDTH = 11;

export interface BoardCell {
  id: string;
  key: string;
  /** The whole value. */
  value: string;
  /** The value as the board draws it. */
  shown: string;
}

export interface Board {
  title: string;
  cells: BoardCell[];
  band: RiskBand;
  footer: string;
}

/** `text`, or its first `width - 1` code points and "…" when it is longer. */
export function clip(text: string, width: number): string {
  const points = Array.from(text);
  return points.length <= width ? text : `${points.slice(0, width - 1).join('')}…`;
}

export function signalsBoard(
  customerId: string | null,
  band: RiskBand,
  rows: readonly SignalRow[],
): Board {
  return {
    title: customerId === null ? 'SIGNALS' : `SIGNALS ${customerId}`,
    cells: rows.map((row) => ({
      id: row.id,
      key: row.key,
      value: row.value,
      shown: clip(row.value, BOARD_VALUE_WIDTH),
    })),
    band,
    footer: `BAND ${band}`,
  };
}

/** The board's cells in two columns, the first column taking the extra cell. */
export function boardColumns(cells: readonly BoardCell[]): [BoardCell[], BoardCell[]] {
  const half = Math.ceil(cells.length / 2);
  return [cells.slice(0, half), cells.slice(half)];
}
