/**
 * `npm run build`'s budget report (spec §9.10, §13): every emitted asset with its raw and gzip size,
 * against three budgets. Exit status 1 means a budget was exceeded.
 *
 * - Initial JavaScript: what `index.html` loads, which is all Classic view ever loads. ≤ 250 KB gzip.
 * - The world chunk: every script `index.html` does not load, which only the office imports
 *   lazily. ≤ 900 KB gzip.
 * - World assets: models and textures under `public/models/`. ≤ 5 MB. The F3 world is procedural,
 *   so there are none.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const MODELS = fileURLToPath(new URL('../public/models/', import.meta.url));
const INITIAL_JS_BUDGET = 250 * 1024;
const WORLD_CHUNK_BUDGET = 900 * 1024;
const WORLD_ASSETS_BUDGET = 5 * 1024 * 1024;

const kilobytes = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`;

function gzipped(path: string): number {
  return gzipSync(readFileSync(path), { level: 9 }).length;
}

const html = readFileSync(`${DIST}index.html`, 'utf8');
const initial = new Set(
  [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((match) => match[1] ?? ''),
);

const rows = readdirSync(`${DIST}assets`)
  .filter((name) => !name.endsWith('.map'))
  .sort()
  .map((name) => {
    const path = `${DIST}assets/${name}`;
    const raw = readFileSync(path).length;
    return { name: `assets/${name}`, raw, gzip: gzipped(path) };
  });

const isFont = (name: string) => /\.(?:woff2?|ttf|otf)$/.test(name);
const line = (name: string, raw: number, gzip: number, mark = '') =>
  process.stdout.write(
    `[bundle] ${name.padEnd(40)} ${kilobytes(raw).padStart(10)} ${kilobytes(gzip).padStart(10)}${mark}\n`,
  );

process.stdout.write(
  `\n[bundle] ${'asset'.padEnd(40)} ${'raw'.padStart(10)} ${'gzip'.padStart(10)}\n`,
);
for (const row of rows.filter((item) => !isFont(item.name))) {
  const mark = initial.has(row.name)
    ? ' (initial)'
    : row.name.endsWith('.js')
      ? ' (world, lazy)'
      : '';
  line(row.name, row.raw, row.gzip, mark);
}
const fonts = rows.filter((item) => isFont(item.name));
line(
  `${fonts.length} font files (loaded on use)`,
  fonts.reduce((sum, row) => sum + row.raw, 0),
  fonts.reduce((sum, row) => sum + row.gzip, 0),
);

const initialGzip = rows
  .filter((row) => initial.has(row.name))
  .reduce((sum, row) => sum + row.gzip, 0);
const worldGzip = rows
  .filter((row) => row.name.endsWith('.js') && !initial.has(row.name))
  .reduce((sum, row) => sum + row.gzip, 0);
const worldAssets = existsSync(MODELS)
  ? readdirSync(MODELS).reduce((sum, name) => sum + statSync(`${MODELS}${name}`).size, 0)
  : 0;

const budgets = [
  ['initial JavaScript', initialGzip, INITIAL_JS_BUDGET, 'gzip'],
  ['world chunk', worldGzip, WORLD_CHUNK_BUDGET, 'gzip'],
  ['world assets', worldAssets, WORLD_ASSETS_BUDGET, 'raw'],
] as const;
let withinBudget = true;
for (const [label, size, budget, measure] of budgets) {
  const within = size <= budget;
  withinBudget &&= within;
  process.stdout.write(
    `[bundle] ${label}: ${kilobytes(size)} ${measure} of ${kilobytes(budget)} ` +
      `(${within ? 'within' : 'OVER'} budget)\n`,
  );
}
process.exit(withinBudget ? 0 : 1);
