/**
 * Boot-time chrome concerns moved out of App.jsx (move-only): the effective
 * dark/light resolution + native titlebar sync, and the startup-loader hold.
 * The pure predicate stays exported so the contract remains unit-testable.
 */
import { useEffect, useState } from 'react';
import { syncNativeTitlebar } from '../utils/nativeTitlebar.js';
import { useOneShotGate } from './useOneShotGate.js';
import { useLinger } from './useLinger.js';

// How long the startup loader stays opaque after its data-hold releases,
// covering the overview's final commit (lazy chart first render).
export const STARTUP_LOADER_LINGER_MS = 250;

/**
 * Returns whether the app is currently rendering dark, taking the saved
 * theme mode and — when it's 'system' — the OS preference into account.
 * Lives with the theme boot logic so the topbar's theme toggle reflects
 * what's on screen rather than the mode literal.
 */
export function useEffectiveDark(themeMode) {
  const [prefersDark, setPrefersDark] = useState(() =>
    typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-color-scheme: dark)').matches
  );
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => setPrefersDark(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  if (themeMode === 'dark') return true;
  if (themeMode === 'light') return false;
  return prefersDark;
}

/**
 * Push the on-screen dark/light theme to the native window titlebar
 * whenever it changes, and once more when the pywebview bridge becomes
 * ready (it can inject after first render). No-op in a browser.
 */
export function useNativeTitlebarSync(effectiveDark) {
  useEffect(() => {
    syncNativeTitlebar(effectiveDark);
    const onReady = () => syncNativeTitlebar(effectiveDark);
    window.addEventListener('pywebviewready', onReady);
    return () => window.removeEventListener('pywebviewready', onReady);
  }, [effectiveDark]);
}

/**
 * Theme boot composition: resolve what's on screen, keep the native
 * titlebar in sync, and hand the topbar its moon/sun toggle.
 *
 * @param {{ themeMode: string, applyMode: (mode: string) => void }} settings
 * @returns {{ effectiveDark: boolean, toggleTheme: () => void }}
 */
export function useStartupTheme(settings) {
  const effectiveDark = useEffectiveDark(settings.themeMode);
  useNativeTitlebarSync(effectiveDark);
  const toggleTheme = () => {
    settings.applyMode(effectiveDark ? 'light' : 'dark');
  };
  return { effectiveDark, toggleTheme };
}

/**
 * Startup-loader hold. Dropping the loader at projectsLoaded hands the user
 * a skeleton flash (loader > skeleton > data) on every boot, so on the
 * default Overview landing it holds until the Overview's data is actually
 * in. It must drop the moment we know no data is coming: load failure,
 * zero local projects, nothing selected, a query error, a restored
 * non-overview tab, or the queries settling empty (`loading` false covers
 * a project with no completed evaluations, whose `accumulated` stays null
 * forever) — every one of those renders its own state and an overlay
 * would wall it off forever. This describes a STATE, not "booting": the
 * caller must scope it with useOneShotGate or a mid-session project
 * switch re-triggers it. Exported for unit tests.
 */
export function shouldShowStartupLoader({
  projectsLoaded, projectsLoadFailed, projectsCount, selectedProject,
  selectedSource, activeTab, dashboard, accumulated, error, loading,
}) {
  if (projectsLoadFailed) return false;
  if (!projectsLoaded) return true;
  if (activeTab !== 'overview') return false;
  if ((projectsCount ?? 0) === 0 && selectedSource !== 'shared') return false;
  if (!selectedProject) return false;
  if (error) return false;
  if (dashboard && accumulated) return false;
  return !!loading;
}

/**
 * The boot-only fullscreen loader signal.
 *
 * One-shot: the hold predicate describes a state a mid-session project
 * switch re-enters (Compare's open-project lands on a not-yet-loaded
 * overview); the gate makes sure the fullscreen loader is boot-only —
 * after it drops once, switches get the overview skeleton instead. Then
 * linger a beat after the hold drops so the overview's final commit (the
 * lazy chart's first render, ~200ms) happens under a still-opaque loader;
 * the fade then reveals a finished page instead of a chart placeholder.
 *
 * @param {Parameters<typeof shouldShowStartupLoader>[0]} inputs
 * @returns {boolean} whether the fullscreen startup loader should show
 */
export function useStartupLoader(inputs) {
  const startupHoldActive = useOneShotGate(shouldShowStartupLoader(inputs));
  return useLinger(startupHoldActive, STARTUP_LOADER_LINGER_MS);
}
