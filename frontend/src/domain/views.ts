/**
 * The two views and their addresses (spec §8.1, D-F-6; the scheme is PROPOSED).
 *
 * Every office address has a Classic twin, and back:
 *
 * | Office              | Classic                   |
 * |---------------------|---------------------------|
 * | `/`                 | `/classic`                |
 * | `/?agent=<id>`      | `/classic/agents/<id>`    |
 * | `/?inbox=1`         | `/classic/inbox`          |
 * | `/brief/<id>`       | `/classic/briefs/<id>`    |
 *
 * So the view toggle, a remembered Classic preference and the WebGL fallback (§9.11) all keep
 * what the reader had open. The common parameters (`as_of`, `snapshot`) travel both ways; the
 * office's own (`agent`, `inbox`, `pixel`, `still`, `perf`) stay in the office.
 */

export type ViewName = 'office' | 'classic';

export type Target =
  | { kind: 'home' }
  | { kind: 'agent'; agentId: string }
  | { kind: 'inbox' }
  | { kind: 'brief'; briefId: string };

export interface Address {
  pathname: string;
  /** Empty, or starting with `?`. */
  search: string;
}

export const OFFICE_PARAMS = {
  agent: 'agent',
  inbox: 'inbox',
  pixel: 'pixel',
  still: 'still',
  perf: 'perf',
} as const;

const OFFICE_ONLY = Object.values(OFFICE_PARAMS);

const CLASSIC_ROOT = '/classic';

function segments(pathname: string): string[] {
  return pathname.split('/').filter((segment) => segment !== '');
}

function decoded(segment: string): string | null {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

function withSearch(pathname: string, params: URLSearchParams): Address {
  const query = params.toString();
  return { pathname, search: query === '' ? '' : `?${query}` };
}

/** The common parameters of `search`, without the office's own. */
function commonParams(search: string): URLSearchParams {
  const params = new URLSearchParams(search);
  for (const name of OFFICE_ONLY) params.delete(name);
  return params;
}

/** Which view an address belongs to: Classic under `/classic`, the office at its own addresses. */
export function viewOf(pathname: string): ViewName | null {
  const parts = segments(pathname);
  if (parts[0] === 'classic') return 'classic';
  if (parts.length === 0) return 'office';
  if (parts[0] === 'brief' && parts.length === 2) return 'office';
  return null;
}

/** What an office address shows, or null for an address that is not the office's. */
export function officeTarget(pathname: string, search: string): Target | null {
  const parts = segments(pathname);
  if (parts.length === 0) {
    const params = new URLSearchParams(search);
    const agentId = params.get(OFFICE_PARAMS.agent);
    if (agentId !== null && agentId !== '') return { kind: 'agent', agentId };
    if (params.get(OFFICE_PARAMS.inbox) === '1') return { kind: 'inbox' };
    return { kind: 'home' };
  }
  if (parts[0] === 'brief' && parts.length === 2) {
    const briefId = decoded(parts[1] as string);
    return briefId === null ? null : { kind: 'brief', briefId };
  }
  return null;
}

/** What a Classic address shows, or null for an address Classic does not have. */
export function classicTarget(pathname: string): Target | null {
  const parts = segments(pathname);
  if (parts[0] !== 'classic') return null;
  if (parts.length === 1) return { kind: 'home' };
  if (parts.length === 2 && parts[1] === 'inbox') return { kind: 'inbox' };
  if (parts.length === 3) {
    const id = decoded(parts[2] as string);
    if (id === null) return null;
    if (parts[1] === 'briefs') return { kind: 'brief', briefId: id };
    if (parts[1] === 'agents') return { kind: 'agent', agentId: id };
  }
  return null;
}

/** The address of `target` in `view`, keeping the common parameters of `search`. */
export function addressOf(view: ViewName, target: Target, search: string): Address {
  const params = commonParams(search);
  if (view === 'classic') {
    switch (target.kind) {
      case 'home':
        return withSearch(CLASSIC_ROOT, params);
      case 'inbox':
        return withSearch(`${CLASSIC_ROOT}/inbox`, params);
      case 'agent':
        return withSearch(`${CLASSIC_ROOT}/agents/${encodeURIComponent(target.agentId)}`, params);
      case 'brief':
        return withSearch(`${CLASSIC_ROOT}/briefs/${encodeURIComponent(target.briefId)}`, params);
    }
  }
  // The office keeps its rendering parameters across its own addresses.
  const office = new URLSearchParams(search);
  for (const name of [OFFICE_PARAMS.pixel, OFFICE_PARAMS.still, OFFICE_PARAMS.perf]) {
    const value = office.get(name);
    if (value !== null) params.set(name, value);
  }
  switch (target.kind) {
    case 'home':
      return withSearch('/', params);
    case 'inbox':
      params.set(OFFICE_PARAMS.inbox, '1');
      return withSearch('/', params);
    case 'agent':
      params.set(OFFICE_PARAMS.agent, target.agentId);
      return withSearch('/', params);
    case 'brief':
      return withSearch(`/brief/${encodeURIComponent(target.briefId)}`, params);
  }
}

/**
 * The twin of an address in the other view. An address the source view does not know maps to
 * the other view's home.
 */
export function twinAddress(to: ViewName, pathname: string, search: string): Address {
  const target =
    (to === 'classic' ? officeTarget(pathname, search) : classicTarget(pathname)) ??
    ({ kind: 'home' } as const);
  return addressOf(to, target, search);
}

/** The remembered view (`aiceohq.view`, §11): Classic only when Classic was chosen. */
export function rememberedView(stored: string | null): ViewName {
  return stored === 'classic' ? 'classic' : 'office';
}

/**
 * Pixel art or smooth toon (D-F-5, §8.1): the URL's `pixel` wins, then the remembered choice
 * (`aiceohq.pixel`); pixel art is the default.
 */
export function pixelArt(param: string | null, stored: string | null): boolean {
  if (param === '0') return false;
  if (param === '1') return true;
  return stored !== '0';
}

/** A `1` flag parameter, such as `still` and `perf` (§8.1). */
export function flag(param: string | null): boolean {
  return param === '1';
}
