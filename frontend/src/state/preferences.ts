/**
 * The reader's remembered choices (spec §11): the pixel-art switch. Each is kept in browser
 * storage as a convenience, inside try/catch; without storage the defaults simply return.
 */

import { create } from 'zustand';

import { STORAGE_KEYS, readStored, writeStored } from '@/lib/storage';

export interface Preferences {
  /** Pixel art (true) or smooth toon (false), D-F-5. */
  pixel: boolean;
  setPixel: (pixel: boolean) => void;
}

export function storedPreferences(): Pick<Preferences, 'pixel'> {
  return { pixel: readStored(STORAGE_KEYS.pixel) !== '0' };
}

export const usePreferences = create<Preferences>()((set) => ({
  ...storedPreferences(),
  setPixel: (pixel) => {
    writeStored(STORAGE_KEYS.pixel, pixel ? '1' : '0');
    set({ pixel });
  },
}));
