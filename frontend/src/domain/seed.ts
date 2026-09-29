/**
 * Deterministic seeds (spec §9.7): an agent's looks, and later its ambient motion, come from a
 * hash of its id, so every demo and screenshot is the same.
 */

/** FNV-1a over the string's UTF-16 code units, as an unsigned 32-bit integer. */
export function hashString(text: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** Mulberry32: a small seeded generator of numbers in [0, 1). */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

/** One item of `choices`, picked by `seed`. */
export function pick<T>(choices: readonly [T, ...T[]], seed: number): T {
  return choices[seed % choices.length] as T;
}
