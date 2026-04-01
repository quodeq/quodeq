/**
 * Shared theme resolution utility.
 * Used by both main.jsx (initial paint) and useAppSettings.js (runtime updates).
 */

/**
 * Compute the data-theme attribute value from mode + family + OS dark preference.
 *
 * @param {string} mode - 'system' | 'light' | 'dark'
 * @param {string} family - theme family name (e.g. 'daruma', 'flynn')
 * @param {boolean} prefersDark - current OS dark-mode preference
 * @returns {string|null} value for data-theme attribute, or null to remove it
 */
export function resolveDataTheme(mode, family, prefersDark) {
  const effectiveMode = mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
  if (family === 'daruma') {
    // System mode: return null so @media (prefers-color-scheme) drives the theme
    // Explicit mode: return 'light' or 'dark' to override OS preference
    return mode === 'system' ? null : effectiveMode;
  }
  return `${family}-${effectiveMode}`;
}
