/**
 * Whether this device can start the 3D office (spec §9.11). The office needs WebGL 2. The probe's
 * own context is released at once, so it does not count against the browser's context limit.
 */

export function canCreateWebGL(): boolean {
  try {
    const context = document.createElement('canvas').getContext('webgl2');
    // A browser without WebGL 2 answers null; a test DOM may answer nothing at all.
    if (!context) return false;
    context.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}
