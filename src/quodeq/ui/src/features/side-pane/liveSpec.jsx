import { useSyncExternalStore } from 'react';

/**
 * A window spec that follows its page.
 *
 * A page registers a spec whose render, copy and download close over the
 * data it holds at that moment, and re-registers only when the spec's id or
 * title change (useRegisterWindowSpec): re-registering on every render would
 * loop with the provider. But the data under a spec moves without either
 * changing. The File and Principle pages, for one, receive the finding detail
 * after their first render, and a registered or docked spec kept printing
 * the rows it was built with. The live spec keeps the page's latest spec in
 * a small store and defers to it: its body re-renders when the page sets a
 * new spec, and copy and download read the current one.
 */

/** A one-value store the page writes and the docked window subscribes to. */
export function createSpecStore(initial) {
  let current = initial;
  const listeners = new Set();
  return {
    get: () => current,
    set(next) {
      if (next === current) return;
      current = next;
      for (const listener of listeners) listener();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

function LiveSpecBody({ store, fallback }) {
  const spec = useSyncExternalStore(store.subscribe, store.get);
  return (spec ?? fallback).render();
}

/**
 * *spec* with its render, copy and download reading *store*'s current spec,
 * falling back to *spec* itself once the page has unregistered.
 * @param {{get: Function, set: Function, subscribe: Function}} store
 * @param {Object} spec
 * @returns {Object}
 */
export function liveSpec(store, spec) {
  const latest = () => store.get() ?? spec;
  return {
    ...spec,
    render: () => <LiveSpecBody store={store} fallback={spec} />,
    copy: spec.copy ? () => latest().copy() : undefined,
    download: spec.download ? () => latest().download() : undefined,
  };
}
