/**
 * Cited text (spec §7.4; DERIVED from `app/evidence/citations.py` `citable_text` and
 * `app/decisions/brief.py` `MAX_QUOTED_SPAN_CHARS`).
 *
 * A document's citable text is `title + "\n" + body_text`, a null part counting as empty. Offsets
 * `[start, end)` are Python string indices, which count Unicode code points, while JavaScript
 * strings index UTF-16 code units. Every slice here is therefore taken over `Array.from(text)`.
 */

/** The separator between a document's title and body (`CITABLE_SEPARATOR`). */
export const CITABLE_SEPARATOR = '\n';

/** A quote's display cap, in code points: the brief's own cap. */
export const MAX_QUOTE_CODE_POINTS = 500;

export function citableText(document: { title: string | null; body_text: string | null }): string {
  return `${document.title ?? ''}${CITABLE_SEPARATOR}${document.body_text ?? ''}`;
}

/** `text[start:end]` as Python computes it, for in-range offsets. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  return Array.from(text).slice(start, end).join('');
}

/** Whether `[start, end)` is a non-empty span inside the text. */
export function spanFits(text: string, start: number, end: number): boolean {
  return start >= 0 && start < end && end <= Array.from(text).length;
}

export interface Quote {
  text: string;
  truncated: boolean;
}

/** The quoted span, capped at 500 code points like the brief's own quotes. */
export function quote(text: string, start: number, end: number): Quote {
  const points = Array.from(text).slice(start, end);
  return points.length > MAX_QUOTE_CODE_POINTS
    ? { text: points.slice(0, MAX_QUOTE_CODE_POINTS).join(''), truncated: true }
    : { text: points.join(''), truncated: false };
}

export interface Highlight {
  before: string;
  span: string;
  after: string;
}

/** The citable text in three parts, so the cited span can be marked. */
export function highlight(text: string, start: number, end: number): Highlight {
  const points = Array.from(text);
  return {
    before: points.slice(0, start).join(''),
    span: points.slice(start, end).join(''),
    after: points.slice(end).join(''),
  };
}
