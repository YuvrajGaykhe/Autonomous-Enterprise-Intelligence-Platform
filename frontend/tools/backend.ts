/**
 * `npm run backend` (make frontend-backend): recreate `<database>_frontend` from clean and serve
 * the working-tree API on 127.0.0.1:8010 until interrupted (spec §12.3, R-F-1).
 *
 * Exit status 2 means the isolated environment could not be used or started. There is no
 * fallback to the development database or the Docker stack.
 */

import { DEV_PORT, DEV_SUFFIX, EnvironmentRefused, startIsolatedBackend } from './lib/isolated.ts';
import { configuredDatabaseUrl } from './lib/settings.ts';

async function main(): Promise<number> {
  if (process.argv.length > 2) {
    process.stderr.write('usage: node tools/backend.ts\n');
    return 2;
  }
  const backend = await startIsolatedBackend({
    suffix: DEV_SUFFIX,
    configuredUrl: configuredDatabaseUrl(),
    port: DEV_PORT,
    quiet: false,
  });
  process.stdout.write(`[isolated] ready: run make frontend-dev and open the printed URL\n`);
  const stopped = new Promise<void>((resolve) => {
    for (const signal of ['SIGINT', 'SIGTERM'] as const) {
      process.once(signal, () => void backend.stop().then(resolve));
    }
    backend.process.once('close', () => resolve());
  });
  await stopped;
  return 0;
}

main().then(
  (status) => process.exit(status),
  (error: unknown) => {
    if (error instanceof EnvironmentRefused) {
      process.stderr.write(`frontend-backend: ${error.message}\n`);
      process.exit(2);
    }
    throw error;
  },
);
