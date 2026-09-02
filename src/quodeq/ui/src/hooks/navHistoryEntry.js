function isScalar(v) {
  return v == null || typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean';
}

/**
 * History state carries only scalars (and arrays of scalars, e.g.
 * preselectDims); object payloads stay in React state and `entriesByIndex`.
 * pushState structured-clones its argument synchronously on the main thread,
 * and entries like evalprinciple/file carry a run's whole findings graph —
 * cloning that inside the click handler froze navigation for seconds before
 * React could even schedule a render (and risks the browser's history-state
 * size cap, which would abort the handler mid-click).
 *
 * Extracted from useNavStack.js verbatim.
 */
export function toHistoryEntry(entry) {
  const light = {};
  for (const [k, v] of Object.entries(entry)) {
    if (isScalar(v) || (Array.isArray(v) && v.every(isScalar))) light[k] = v;
  }
  return light;
}

export function handlePopState(e, setNavStack, entriesByIndex) {
  const targetIndex = e.state?.navIndex ?? 0;
  setNavStack((prev) => {
    if (targetIndex < prev.length - 1) {
      return prev.slice(0, targetIndex + 1);
    }
    if (targetIndex >= prev.length && e.state?.entry) {
      // Forward: the full entry (with its object payload) lives in
      // entriesByIndex; the history-state copy is the scalar-only fallback
      // for entries pushed before a reload.
      const entry = entriesByIndex.get(targetIndex) || e.state.entry;
      return [...prev.slice(0, targetIndex), entry];
    }
    return prev;
  });
}
