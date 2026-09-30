/**
 * The reader's remembered choices (spec §11): the pixel-art switch and sound (off by default,
 * D-F-19). Each is kept in browser storage as a convenience, inside try/catch; without storage the
 * defaults simply return.
 */

import { create } from 'zustand';

import { STORAGE_KEYS, readStored, writeStored } from '@/lib/storage';

export interface Preferences {
  /** Pixel art (true) or smooth toon (false), D-F-5. */
  pixel: boolean;
  /** Sound on; off unless the reader turned it on (D-F-19). */
  sound: boolean;
  setPixel: (pixel: boolean) => void;
  setSound: (sound: boolean) => void;
}

export function storedPreferences(): Pick<Preferences, 'pixel' | 'sound'> {
  return {
    pixel: readStored(STORAGE_KEYS.pixel) !== '0',
    sound: readStored(STORAGE_KEYS.sound) === '1',
  };
}

export const usePreferences = create<Preferences>()((set) => ({
  ...storedPreferences(),
  setPixel: (pixel) => {
    writeStored(STORAGE_KEYS.pixel, pixel ? '1' : '0');
    set({ pixel });
  },
  setSound: (sound) => {
    writeStored(STORAGE_KEYS.sound, sound ? '1' : '0');
    set({ sound });
  },
}));
