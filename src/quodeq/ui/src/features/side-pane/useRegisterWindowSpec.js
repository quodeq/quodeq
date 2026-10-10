import { useCallback, useEffect, useRef } from 'react';
import { useSidePane } from './SidePaneContext.jsx';
import { createSpecStore, liveSpec } from './liveSpec.jsx';

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
  // and register a live spec that reads the latest closures from a store
  // (liveSpec.jsx). This keeps the dock title in sync when it changes (e.g.
  // file detail with a different filter) and lets a registered or docked
  // window follow data updates (the finding detail arriving after the first
  // render, say) without re-registering for them.
  const store = useRef(null);
  if (store.current === null) store.current = createSpecStore(spec);
  useEffect(() => { store.current.set(spec); }, [spec]);
  // One live spec per visible identity (id + title). The effect below also
  // re-runs when the dock changes (hasWindow), and replaceWindow
  // short-circuits only on the same object: a fresh wrapper per run, or per
  // page spec object (a consumer's spec is often fresh every render), would
  // re-set the windows, change hasWindow, and loop. Data updates reach the
  // wrapper through the store, so it only needs rebuilding when the identity
  // it shows changes.
  const wrapper = useRef(null);
  const liveFor = useCallback((pageSpec) => {
    const cached = wrapper.current;
    if (cached && cached.id === pageSpec.id && cached.title === pageSpec.title) return cached;
    wrapper.current = liveSpec(store.current, pageSpec);
    return wrapper.current;
  }, []);
  const specId = spec?.id ?? null;
  const specTitle = spec?.title ?? null;

  useEffect(() => {
    if (!specId) {
      unregisterSpec(type);
      return undefined;
    }
    const live = liveFor(store.current.get());
    registerSpec(type, live);
    if (hasWindow(live.id)) {
      replaceWindow(live);
    }
    return () => unregisterSpec(type);
  }, [type, specId, specTitle, registerSpec, unregisterSpec, replaceWindow, hasWindow, liveFor]);

  const isInDock = spec ? hasWindow(spec.id) : false;
  const isAtCap = windows.length >= MAX_WINDOWS;

  return {
    spec: spec ?? null,
    hasWindow: isInDock,
    isAtCap,
    toggle: () => { if (spec) toggleWindow(liveFor(spec)); },
  };
}
