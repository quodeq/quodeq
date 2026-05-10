import { useEffect } from 'react';
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

  useEffect(() => {
    if (!spec) {
      unregisterSpec(type);
      return undefined;
    }
    registerSpec(type, spec);
    if (hasWindow(spec.id)) {
      replaceWindow(spec);
    }
    return () => unregisterSpec(type);
  }, [type, spec, registerSpec, unregisterSpec, replaceWindow, hasWindow]);

  const isInDock = spec ? hasWindow(spec.id) : false;
  const isAtCap = windows.length >= MAX_WINDOWS;

  return {
    spec: spec ?? null,
    hasWindow: isInDock,
    isAtCap,
    toggle: () => { if (spec) toggleWindow(spec); },
  };
}
