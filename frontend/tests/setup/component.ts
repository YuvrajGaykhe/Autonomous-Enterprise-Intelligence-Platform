import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { initialCamera, useCamera } from '@/state/camera';
import { storedPreferences, usePreferences } from '@/state/preferences';
import { initialSession, useSession } from '@/state/session';

import { server } from '../support/server';

// A page waits for several requests before it renders; give findBy and waitFor room on a loaded
// machine rather than fail on timing.
configure({ asyncUtilTimeout: 5000 });

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  // The session store and browser storage outlive a render; every test starts clean.
  useSession.setState(initialSession);
  useCamera.setState(initialCamera);
  window.localStorage.clear();
  usePreferences.setState(storedPreferences());
});
afterAll(() => server.close());
