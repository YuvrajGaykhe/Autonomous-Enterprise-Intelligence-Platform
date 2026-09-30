/**
 * The build-time variables the app reads (spec §6.1). Vite embeds `VITE_*` values in the client
 * bundle, so none of them may carry a secret.
 */

interface ImportMetaEnv {
  /** Set by Vercel while it builds the hosted demo: `preview` or `production`. */
  readonly VITE_VERCEL_ENV?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
