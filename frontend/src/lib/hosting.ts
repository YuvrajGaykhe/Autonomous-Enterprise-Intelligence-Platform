/**
 * Whether this build is the hosted demo (spec §14 F5). Vercel sets `VITE_VERCEL_ENV` during the
 * build (`preview` or `production`); a local build leaves it unset. It carries no secret (§6.1).
 */

export const HOSTED: boolean = (import.meta.env.VITE_VERCEL_ENV ?? '') !== '';
