/**
 * The two views' addresses (spec §8.1, D-F-6): each office address has a Classic twin, the common
 * parameters travel, the office's own stay; and the remembered choices (§11).
 */

import { describe, expect, it } from 'vitest';

import {
  addressOf,
  classicTarget,
  flag,
  officeTarget,
  pixelArt,
  rememberedView,
  twinAddress,
  viewOf,
} from '@/domain/views';

describe('which view an address belongs to', () => {
  it.each([
    ['/', 'office'],
    ['/brief/b1', 'office'],
    ['/classic', 'classic'],
    ['/classic/briefs/b1', 'classic'],
    ['/brief', null],
    ['/brief/b1/extra', null],
    ['/nowhere', null],
  ] as const)('%s is %s', (pathname, view) => {
    expect(viewOf(pathname)).toBe(view);
  });
});

describe('what an office address shows', () => {
  it('reads home, an agent, the inbox and a brief', () => {
    expect(officeTarget('/', '')).toEqual({ kind: 'home' });
    expect(officeTarget('/', '?agent=linker&inbox=1')).toEqual({
      kind: 'agent',
      agentId: 'linker',
    });
    expect(officeTarget('/', '?agent=&inbox=1')).toEqual({ kind: 'inbox' });
    expect(officeTarget('/', '?inbox=0')).toEqual({ kind: 'home' });
    expect(officeTarget('/brief/a%20b', '')).toEqual({ kind: 'brief', briefId: 'a b' });
  });

  it('knows no other address, nor a brief id that is not valid percent-encoding', () => {
    expect(officeTarget('/classic', '')).toBeNull();
    expect(officeTarget('/brief/%E0%A4%A', '')).toBeNull();
  });
});

describe('what a Classic address shows', () => {
  it('reads home, the inbox, a brief and an agent', () => {
    expect(classicTarget('/classic')).toEqual({ kind: 'home' });
    expect(classicTarget('/classic/inbox')).toEqual({ kind: 'inbox' });
    expect(classicTarget('/classic/briefs/b%2F1')).toEqual({ kind: 'brief', briefId: 'b/1' });
    expect(classicTarget('/classic/agents/csv_demo')).toEqual({
      kind: 'agent',
      agentId: 'csv_demo',
    });
  });

  it('knows no other address', () => {
    expect(classicTarget('/')).toBeNull();
    expect(classicTarget('/classic/inbox/more')).toBeNull();
    expect(classicTarget('/classic/briefs')).toBeNull();
    expect(classicTarget('/classic/unknown/x')).toBeNull();
    expect(classicTarget('/classic/agents/%E0%A4%A')).toBeNull();
  });
});

describe('addresses', () => {
  const search = '?as_of=2026-09-18&snapshot=1d891b0b543f&agent=memory&pixel=0&still=1&perf=1';

  it('drops the office parameters on the way to Classic', () => {
    expect(addressOf('classic', { kind: 'home' }, search)).toEqual({
      pathname: '/classic',
      search: '?as_of=2026-09-18&snapshot=1d891b0b543f',
    });
    expect(addressOf('classic', { kind: 'inbox' }, '')).toEqual({
      pathname: '/classic/inbox',
      search: '',
    });
    expect(addressOf('classic', { kind: 'agent', agentId: 'a b' }, '').pathname).toBe(
      '/classic/agents/a%20b',
    );
    expect(addressOf('classic', { kind: 'brief', briefId: 'b1' }, '').pathname).toBe(
      '/classic/briefs/b1',
    );
  });

  it('keeps the rendering parameters inside the office, and sets its own panel', () => {
    expect(addressOf('office', { kind: 'home' }, search)).toEqual({
      pathname: '/',
      search: '?as_of=2026-09-18&snapshot=1d891b0b543f&pixel=0&still=1&perf=1',
    });
    expect(addressOf('office', { kind: 'inbox' }, '?agent=memory')).toEqual({
      pathname: '/',
      search: '?inbox=1',
    });
    expect(addressOf('office', { kind: 'agent', agentId: 'linker' }, '?inbox=1')).toEqual({
      pathname: '/',
      search: '?agent=linker',
    });
    expect(addressOf('office', { kind: 'brief', briefId: 'b 1' }, '?as_of=auto')).toEqual({
      pathname: '/brief/b%201',
      search: '?as_of=auto',
    });
  });

  it('maps each address to its twin in the other view', () => {
    expect(twinAddress('classic', '/', '?agent=linker&as_of=auto')).toEqual({
      pathname: '/classic/agents/linker',
      search: '?as_of=auto',
    });
    expect(twinAddress('classic', '/', '?inbox=1')).toEqual({
      pathname: '/classic/inbox',
      search: '',
    });
    expect(twinAddress('classic', '/brief/b1', '').pathname).toBe('/classic/briefs/b1');
    expect(twinAddress('office', '/classic/agents/linker', '?as_of=auto')).toEqual({
      pathname: '/',
      search: '?as_of=auto&agent=linker',
    });
    expect(twinAddress('office', '/classic/briefs/b1', '').pathname).toBe('/brief/b1');
  });

  it('sends an address the source view does not know to the other view home', () => {
    expect(twinAddress('office', '/nowhere', '?as_of=auto')).toEqual({
      pathname: '/',
      search: '?as_of=auto',
    });
    expect(twinAddress('classic', '/nowhere', '')).toEqual({ pathname: '/classic', search: '' });
  });
});

describe('remembered choices (§11)', () => {
  it('remembers Classic only when Classic was chosen', () => {
    expect(rememberedView('classic')).toBe('classic');
    expect(rememberedView('office')).toBe('office');
    expect(rememberedView(null)).toBe('office');
  });

  it('lets the URL decide pixel art, then the remembered choice, then pixel art', () => {
    expect(pixelArt('0', '1')).toBe(false);
    expect(pixelArt('1', '0')).toBe(true);
    expect(pixelArt(null, '0')).toBe(false);
    expect(pixelArt(null, '1')).toBe(true);
    expect(pixelArt('yes', null)).toBe(true);
  });

  it('reads a flag parameter as on only when it is 1', () => {
    expect(flag('1')).toBe(true);
    expect(flag('true')).toBe(false);
    expect(flag(null)).toBe(false);
  });
});
