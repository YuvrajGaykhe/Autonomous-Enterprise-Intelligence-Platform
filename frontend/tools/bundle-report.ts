/**
 * `npm run build`'s budget report (spec §9.10, §13): every emitted asset with its raw and gzip size,
 * and the initial JavaScript (what `index.html` loads, which is the Classic view path) against its
 * 250 KB gzip budget. Exit status 1 means a budget was exceeded.
 *
 * The world chunk (≤ 900 KB gzip, loaded lazily) and the world assets (≤ 5 MB) are checked from
 * F3, when they exist.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const INITIAL_JS_BUDGET = 250 * 1024;

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
  line(row.name, row.raw, row.gzip, initial.has(row.name) ? ' (initial)' : '');
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
const withinBudget = initialGzip <= INITIAL_JS_BUDGET;
process.stdout.write(
  `[bundle] initial JavaScript: ${kilobytes(initialGzip)} gzip of ${kilobytes(INITIAL_JS_BUDGET)} ` +
    `(${withinBudget ? 'within' : 'OVER'} budget)\n`,
);
process.exit(withinBudget ? 0 : 1);
