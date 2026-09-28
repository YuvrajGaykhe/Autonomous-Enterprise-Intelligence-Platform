/**
 * The guards of spec §12.4: no fake data, no score, complete notices, the honesty copy and the
 * naming rule (R-F-3). Sources are parsed with the TypeScript compiler, so comments are never
 * checked as code and prose inside a string is never checked as a name.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { relative, resolve } from 'node:path';

import ts from 'typescript';
import { describe, expect, it } from 'vitest';

import { FRONTEND_ROOT, REPO_ROOT } from '../support/fixtures';

/**
 * The scanner's name pattern, copied from `scripts/secret_scan.py` (`SECRET_NAME`, unchanged since
 * `b461c58`). A test below fails if the scanner's pattern ever differs from this copy.
 */
const SCANNER_NAME_PATTERN = String.raw`(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)`;

/**
 * Keys the frozen backend defines and the frontend must mirror verbatim (owner ruling, F1).
 * Each is named with the code that emits it; every other name is checked.
 */
const API_DEFINED_NAMES = new Map([
  ['matched_token', 'app/intelligence/contract.py DerivedLink.to_payload (payload §0.6.13.1)'],
]);

/** Domain id literals (§12.4). PROJ and ORG are added because the dataset's ids use them. */
const DOMAIN_ID = /\b(?:CUST|TKT|DEAL|DOC|EMP|PRJ|PROJ|ORG)-\d{3}\b/;

const SOURCE_EXTENSIONS = /\.(?:ts|tsx|js|mjs)$/;

function walk(directory: string, skip: (path: string) => boolean = () => false): string[] {
  if (!existsSync(directory)) return [];
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    if (skip(path)) return [];
    return statSync(path).isDirectory() ? walk(path, skip) : [path];
  });
}

const frontendPath = (path: string) => relative(FRONTEND_ROOT, path);
const SRC = resolve(FRONTEND_ROOT, 'src');
const GENERATED = resolve(SRC, 'api/generated');
const srcFiles = walk(SRC).filter((path) => SOURCE_EXTENSIONS.test(path));
const handWrittenSrc = srcFiles.filter((path) => !path.startsWith(GENERATED));

function parse(path: string): ts.SourceFile {
  const kind = path.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  return ts.createSourceFile(path, readFileSync(path, 'utf8'), ts.ScriptTarget.Latest, true, kind);
}

/** Every piece of literal text in a file: strings, template parts and JSX text. */
function literalTexts(path: string): string[] {
  const texts: string[] = [];
  const visit = (node: ts.Node) => {
    if (
      ts.isStringLiteral(node) ||
      ts.isNoSubstitutionTemplateLiteral(node) ||
      ts.isTemplateHead(node) ||
      ts.isTemplateMiddle(node) ||
      ts.isTemplateTail(node) ||
      ts.isJsxText(node)
    ) {
      texts.push(node.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(parse(path));
  return texts;
}

/** Every name a file declares or uses: identifiers and quoted property names. */
function namesIn(path: string): string[] {
  const names: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isIdentifier(node) || ts.isPrivateIdentifier(node)) names.push(node.text);
    if (
      (ts.isPropertyAssignment(node) || ts.isPropertySignature(node)) &&
      (ts.isStringLiteral(node.name) || ts.isNoSubstitutionTemplateLiteral(node.name))
    ) {
      names.push(node.name.text);
    }
    if (ts.isJsxAttribute(node)) names.push(node.name.getText());
    ts.forEachChild(node, visit);
  };
  visit(parse(path));
  return names;
}

function jsonKeys(value: unknown): string[] {
  if (Array.isArray(value)) return value.flatMap(jsonKeys);
  if (value !== null && typeof value === 'object') {
    return Object.entries(value).flatMap(([key, child]) => [key, ...jsonKeys(child)]);
  }
  return [];
}

describe('no fake data (§12.4, AC-F-1)', () => {
  it('src/ holds no customer, ticket, deal, document, employee, project or organization id', () => {
    const found = srcFiles.flatMap((path) =>
      literalTexts(path)
        .filter((text) => DOMAIN_ID.test(text))
        .map((text) => `${frontendPath(path)}: ${JSON.stringify(text)}`),
    );
    expect(found).toEqual([]);
  });
});

describe('no score (§12.4, AC-F-3, D-F-2)', () => {
  it('src/ renders no percentage and no out-of-100 figure', () => {
    const found = handWrittenSrc.flatMap((path) =>
      literalTexts(path)
        .filter((text) => text.includes('%') || /\/\s*100\b/.test(text))
        .map((text) => `${frontendPath(path)}: ${JSON.stringify(text)}`),
    );
    expect(found).toEqual([]);
  });
});

describe('notices (§12.4, AC-F-11)', () => {
  it('lists every vendored file and every model in THIRD_PARTY_NOTICES.md', () => {
    const notices = readFileSync(resolve(FRONTEND_ROOT, 'THIRD_PARTY_NOTICES.md'), 'utf8');
    const listed = [
      ...walk(resolve(SRC, 'vendor')),
      ...walk(resolve(FRONTEND_ROOT, 'public/models')),
    ].map(frontendPath);
    expect(listed.filter((path) => !notices.includes(path))).toEqual([]);
  });

  it('lists every file adapted from shadcn/ui', () => {
    const notices = readFileSync(resolve(FRONTEND_ROOT, 'THIRD_PARTY_NOTICES.md'), 'utf8');
    const adapted = walk(resolve(SRC, 'ui'))
      .filter((path) => readFileSync(path, 'utf8').includes('Adapted from shadcn/ui'))
      .map(frontendPath);
    expect(adapted.length).toBeGreaterThan(0);
    expect(adapted.filter((path) => !notices.includes(path))).toEqual([]);
  });
});

/** Appendix A's backticked strings, with `<name>` placeholders written as `{name}`. */
function appendixStrings(): string[] {
  const spec = readFileSync(`${REPO_ROOT}CONTEXT/FRONTEND_SPECIFICATION.md`, 'utf8');
  const appendix = spec.slice(spec.indexOf('## Appendix A: fixed copy'));
  return [...appendix.matchAll(/^\|[^|\n]+\|\s*`([^`]+)`\s*\|\s*$/gm)].map((match) =>
    (match[1] ?? '').replace(/<(\w+)>/g, '{$1}'),
  );
}

describe('honesty copy (§12.4, AC-F-15)', () => {
  const strings = appendixStrings();
  const texts = srcFiles.flatMap(literalTexts);

  it('reads all fifteen fixed strings and nine role lines from Appendix A', () => {
    expect(strings).toHaveLength(24);
  });

  it.each(strings)('%j exists exactly once in src/', (text) => {
    const occurrences = texts.filter((literal) => literal.includes(text)).length;
    expect(occurrences).toBe(1);
  });
});

describe('the naming rule (§11, §12.4, R-F-3)', () => {
  const pattern = new RegExp(SCANNER_NAME_PATTERN, 'i');
  const flagged = (name: string) => pattern.test(name) && !API_DEFINED_NAMES.has(name);

  it("copies the scanner's own name pattern", () => {
    const scanner = readFileSync(`${REPO_ROOT}scripts/secret_scan.py`, 'utf8');
    const declared = /^SECRET_NAME = r"(.+)"$/m.exec(scanner);
    expect(declared?.[1]).toBe(SCANNER_NAME_PATTERN);
  });

  it('exempts only names the frozen backend defines, and each is really used', () => {
    const payloadSchema = readFileSync(resolve(SRC, 'api/schemas/briefPayloadV1.ts'), 'utf8');
    for (const name of API_DEFINED_NAMES.keys()) {
      expect(payloadSchema).toContain(`${name}:`);
      expect(readFileSync(`${REPO_ROOT}app/intelligence/contract.py`, 'utf8')).toContain(
        `"${name}"`,
      );
    }
  });

  it('holds for every identifier and key in frontend source, tooling and tests', () => {
    const files = [
      ...handWrittenSrc,
      ...walk(resolve(FRONTEND_ROOT, 'tools')),
      ...walk(resolve(FRONTEND_ROOT, 'tests'), (path) => path.endsWith('/fixtures')),
      ...['vite.config.ts', 'vitest.config.ts', 'playwright.config.ts', 'eslint.config.js'].map(
        (name) => resolve(FRONTEND_ROOT, name),
      ),
    ].filter((path) => SOURCE_EXTENSIONS.test(path));
    const found = files.flatMap((path) =>
      namesIn(path)
        .filter(flagged)
        .map((name) => `${frontendPath(path)}: ${name}`),
    );
    expect(found).toEqual([]);
  });

  it('holds for every key in the fixtures and the JSON configuration', () => {
    const files = [
      ...walk(resolve(FRONTEND_ROOT, 'tests/fixtures')),
      ...['package.json', 'tsconfig.json', 'tsconfig.app.json', 'tsconfig.node.json'].map((name) =>
        resolve(FRONTEND_ROOT, name),
      ),
      resolve(FRONTEND_ROOT, 'components.json'),
      resolve(FRONTEND_ROOT, '.prettierrc.json'),
    ];
    const found = files.flatMap((path) =>
      jsonKeys(JSON.parse(readFileSync(path, 'utf8')) as unknown)
        .filter(flagged)
        .map((key) => `${frontendPath(path)}: ${key}`),
    );
    expect(found).toEqual([]);
  });

  it('holds for every theme variable in the stylesheets', () => {
    const found = walk(resolve(SRC, 'styles')).flatMap((path) =>
      [...readFileSync(path, 'utf8').matchAll(/--[\w-]+/g)]
        .map((match) => match[0])
        .filter(flagged)
        .map((name) => `${frontendPath(path)}: ${name}`),
    );
    expect(found).toEqual([]);
  });
});
