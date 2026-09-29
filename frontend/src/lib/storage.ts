/**
 * Browser storage for conveniences only (spec §11): every read and write is inside try/catch, and
 * the app works the same when storage is unavailable.
 */

export const STORAGE_KEYS = {
  actorName: 'aiceohq.actorName',
  view: 'aiceohq.view',
  pixel: 'aiceohq.pixel',
} as const;

export function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage is a convenience; without it the name is simply not remembered.
  }
}
