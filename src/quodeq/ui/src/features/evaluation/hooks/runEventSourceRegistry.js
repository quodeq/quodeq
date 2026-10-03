/**
 * One EventSource per run, shared by every subscriber.
 *
 * useRunEventStream used to open its own EventSource per call, so a History
 * page with five rows for the same run held five connections to the same
 * endpoint (and browsers cap SSE connections per origin at six). Streams are
 * now ref-counted here: the first acquirer opens the source, later ones
 * share it, and the last release closes it.
 *
 * The registry is keyed by QueryClient first so that cache writes land in
 * the client the subscriber renders under, and so tests with a fresh client
 * each never see another test's stream.
 *
 * Each stream also tracks a connection state (see STREAM_STATE) that the
 * polling policy reads: an errored stream means the cache may be stale, so
 * the status query switches back to a fast poll until it recovers.
 */
import { runEventsUrl } from "../../../api/evaluations.js";

export const STREAM_STATE = Object.freeze({
  IDLE: "idle",       // no stream for this run (SSE off, no job id, or closed)
  OPEN: "open",       // connected, or connecting for the first time
  ERROR: "error",     // connection dropped; the browser is retrying or gave up
});

/** @type {WeakMap<object, {streams: Map<string, {source: EventSource, refs: number, state: string}>, listeners: Map<string, Set<Function>>}>} */
const byClient = new WeakMap();

// Listeners live beside the streams, not on them: a subscriber may register
// before the stream exists (useSyncExternalStore subscribes in its own
// effect) and must still hear the stream open and close.
function registryFor(queryClient) {
  let registry = byClient.get(queryClient);
  if (!registry) {
    registry = { streams: new Map(), listeners: new Map() };
    byClient.set(queryClient, registry);
  }
  return registry;
}

function notify(registry, jobId) {
  registry.listeners.get(jobId)?.forEach((fn) => fn());
}

function setState(registry, jobId, entry, state) {
  if (entry.state === state) return;
  entry.state = state;
  notify(registry, jobId);
}

function openEntry(registry, jobId, wire) {
  const source = new EventSource(runEventsUrl(jobId));
  const entry = { source, refs: 0, state: STREAM_STATE.OPEN };
  source.onopen = () => setState(registry, jobId, entry, STREAM_STATE.OPEN);
  source.onerror = () => setState(registry, jobId, entry, STREAM_STATE.ERROR);
  wire(source, () => {
    source.close();
    setState(registry, jobId, entry, STREAM_STATE.IDLE);
  });
  return entry;
}

/**
 * Take a reference on the run's stream, opening it on first use. `wire` is
 * invoked once per opened source with `(source, finish)`, where `finish`
 * closes the stream for good (the run is over).
 *
 * @returns {() => void} release; closes the source when the last ref goes
 */
export function acquireRunStream(queryClient, jobId, wire) {
  const registry = registryFor(queryClient);
  let entry = registry.streams.get(jobId);
  if (!entry) {
    entry = openEntry(registry, jobId, wire);
    registry.streams.set(jobId, entry);
    notify(registry, jobId);
  }
  entry.refs += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    entry.refs -= 1;
    if (entry.refs > 0) return;
    entry.source.close();
    registry.streams.delete(jobId);
    notify(registry, jobId);
  };
}

/** Connection state of the run's shared stream, IDLE when none is open. */
export function getRunStreamState(queryClient, jobId) {
  return byClient.get(queryClient)?.streams.get(jobId)?.state ?? STREAM_STATE.IDLE;
}

/**
 * Subscribe to state changes of the run's stream. Shaped for
 * useSyncExternalStore: returns the unsubscribe function.
 */
export function subscribeRunStream(queryClient, jobId, onChange) {
  const { listeners } = registryFor(queryClient);
  let set = listeners.get(jobId);
  if (!set) {
    set = new Set();
    listeners.set(jobId, set);
  }
  set.add(onChange);
  return () => {
    set.delete(onChange);
    if (set.size === 0) listeners.delete(jobId);
  };
}
