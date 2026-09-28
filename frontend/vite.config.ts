/**
 * Vite: React, Tailwind and the `/api` proxy (spec §6.1).
 *
 * In development and preview, `/api` goes to FRONTEND_API_TARGET, which defaults to the
 * isolated working-tree API of `make frontend-backend` (R-F-1). Production serves the API on
 * the same origin, so the backend never enables CORS.
 */

import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const apiTarget = process.env['FRONTEND_API_TARGET'] ?? 'http://127.0.0.1:8010';
const proxy = { '/api': { target: apiTarget } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 5173, proxy },
  preview: { host: '127.0.0.1', port: 4173, proxy },
  build: { sourcemap: true },
});
