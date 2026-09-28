import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { initialSession, useSession } from '@/state/session';

import { server } from '../support/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  // The session store and browser storage outlive a render; every test starts clean.
  useSession.setState(initialSession);
  window.localStorage.clear();
});
afterAll(() => server.close());
