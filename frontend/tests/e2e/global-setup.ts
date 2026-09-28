/**
 * End-to-end environment (spec §12.3): recreate `<database>_frontend_e2e` from clean, serve the
 * working-tree API over it on an OS-assigned port, and serve the production build through
 * `vite preview` with `/api` proxied to that API. Exit status 2 conditions of the tooling fail
 * the run; there is no fallback.
 */

import { resolve } from 'node:path';

import { preview } from 'vite';

import { E2E_SUFFIX, freePort, startIsolatedBackend } from '../../tools/lib/isolated.ts';
import { configuredDatabaseUrl } from '../../tools/lib/settings.ts';

export const BASE_URL_VARIABLE = 'AICEOHQ_E2E_BASE_URL';
export const API_URL_VARIABLE = 'AICEOHQ_E2E_API_URL';

export default async function globalSetup(): Promise<() => Promise<void>> {
  const backend = await startIsolatedBackend({
    suffix: E2E_SUFFIX,
    configuredUrl: configuredDatabaseUrl(),
    port: 0,
    quiet: true,
  });
  try {
    process.env['FRONTEND_API_TARGET'] = backend.baseUrl;
    const port = await freePort();
    const server = await preview({
      configFile: resolve(import.meta.dirname, '../../vite.config.ts'),
      preview: { port, strictPort: true },
    });
    process.env[BASE_URL_VARIABLE] = `http://127.0.0.1:${port}`;
    process.env[API_URL_VARIABLE] = backend.baseUrl;
    return async () => {
      await new Promise<void>((done) => server.httpServer.close(() => done()));
      await backend.stop();
    };
  } catch (error) {
    await backend.stop();
    throw error;
  }
}
