import { applyInitialTheme } from './applyInitialTheme.js';

/**
 * Boot-time fault-isolation boundary around applyInitialTheme(): a failure
 * here (e.g. storage access blocked) must not stop the rest of main.jsx's
 * boot sequence from running.
 */
export function bootTheme(applyTheme = applyInitialTheme) {
  try {
    applyTheme();
  } catch (err) {
    console.warn('[main] initial theme apply failed:', err);
  }
}
