import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';

import { TOUR_SEEN } from '@/domain/tour';
import { STORAGE_KEYS } from '@/lib/storage';
import { initialCamera, useCamera } from '@/state/camera';
import { directorClock, useDirector } from '@/state/director';
import { storedPreferences, usePreferences } from '@/state/preferences';
import { initialSession, useSession } from '@/state/session';
import { initialTour, useTour } from '@/state/tour';

import { server } from '../support/server';

// A page waits for several requests before it renders; give findBy and waitFor room on a loaded
// machine rather than fail on timing.
configure({ asyncUtilTimeout: 5000 });

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
// Every test is a returning reader, who has seen the tour (F6); the tour's own tests clear this.
beforeEach(() => window.localStorage.setItem(STORAGE_KEYS.tour, TOUR_SEEN));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  // The session store and browser storage outlive a render; every test starts clean.
  useSession.setState(initialSession);
  useTour.setState(initialTour);
  useCamera.setState(initialCamera);
  useDirector.getState().end();
  useDirector.setState({ stamp: null });
  directorClock.now = () => performance.now();
  window.localStorage.clear();
  usePreferences.setState(storedPreferences());
});
afterAll(() => server.close());
