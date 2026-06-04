import { useEffect, useRef } from 'react';
import { useSidePane } from './SidePaneContext.jsx';

/**
 * Registers a window spec for a given type while the calling component is
 * mounted. The spec is *available* (the toolbar can add it on click) but is
 * not added to the dock until the user toggles it.
 *
 * Returns helpers the toolbar button uses to render its state.
 */
export function useRegisterWindowSpec(type, spec) {
  const ctx = useSidePane();
  const { registerSpec, unregisterSpec, replaceWindow, hasWindow, toggleWindow, windows, MAX_WINDOWS } = ctx;

  // The consumer's spec is typically a fresh object on every render — it
  // closes over computed values (filteredAccumulated, activeFilter, etc.).
  // Re-running this effect on every spec identity change would call
  // registerSpec/replaceWindow on every render, looping with the provider's
  // setState and pegging React's "Maximum update depth" warning.
  //
  // Instead, anchor the effect on the spec's visible identity (id + title)
  // and read the current closures from a ref. This keeps the dock title in
  // sync when it changes (e.g. file detail with a different filter) while
  // ignoring closure-only churn from data updates.
  const specRef = useRef(spec);
  specRef.current = spec;
  const specId = spec?.id ?? null;
  const specTitle = spec?.title ?? null;

  useEffect(() => {
    if (!specId) {
      unregisterSpec(type);
      return undefined;
    }
    const current = specRef.current;
    registerSpec(type, current);
    if (hasWindow(current.id)) {
      replaceWindow(current);
    }
    return () => unregisterSpec(type);
  }, [type, specId, specTitle, registerSpec, unregisterSpec, replaceWindow, hasWindow]);

  const isInDock = spec ? hasWindow(spec.id) : false;
  const isAtCap = windows.length >= MAX_WINDOWS;

  return {
    spec: spec ?? null,
    hasWindow: isInDock,
    isAtCap,
    toggle: () => { if (spec) toggleWindow(spec); },
  };
}
