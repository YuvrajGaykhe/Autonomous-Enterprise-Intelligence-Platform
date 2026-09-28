/**
 * Vitest layers (spec §12.1): unit, component, contract, guards and tools.
 *
 * Coverage covers `src/`; `src/domain/**` and `src/api/**` must stay at 100% of lines,
 * branches, functions and statements.
 */

import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config.ts';

const complete = { lines: 100, branches: 100, functions: 100, statements: 100 };

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      projects: [
        {
          extends: true,
          test: { name: 'unit', include: ['tests/unit/**/*.test.ts'], environment: 'jsdom' },
        },
        {
          extends: true,
          test: {
            name: 'component',
            include: ['tests/component/**/*.test.tsx'],
            environment: 'jsdom',
            setupFiles: ['tests/setup/component.ts'],
          },
        },
        {
          extends: true,
          test: { name: 'contract', include: ['tests/contract/**/*.test.ts'], environment: 'node' },
        },
        {
          extends: true,
          test: { name: 'guards', include: ['tests/guards/**/*.test.ts'], environment: 'node' },
        },
        {
          extends: true,
          test: { name: 'tools', include: ['tests/tools/**/*.test.ts'], environment: 'node' },
        },
      ],
      coverage: {
        provider: 'v8',
        include: ['src/**/*.{ts,tsx}'],
        exclude: ['src/api/generated/**', 'src/**/*.d.ts'],
        reporter: ['text', 'json-summary'],
        reportsDirectory: 'coverage',
        thresholds: { 'src/api/**': complete, 'src/domain/**': complete },
      },
    },
  }),
);
