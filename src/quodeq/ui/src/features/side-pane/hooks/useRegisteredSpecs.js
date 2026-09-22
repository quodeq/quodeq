import { useCallback, useState } from 'react';

/**
 * SidePaneProvider.jsx's registered-window-spec-by-type registry, extracted
 * verbatim (additive split only — no reducer rewrite; the context value
 * shape SidePaneProvider builds from this hook's return stays
 * byte-identical to before the split).
 */
export function useRegisteredSpecs() {
  const [registeredSpecs, setRegisteredSpecs] = useState({}); // { [type]: spec }

  const registerSpec = useCallback((type, spec) => {
    setRegisteredSpecs((prev) => {
      if (prev[type] === spec) return prev;
      return { ...prev, [type]: spec };
    });
  }, []);

  const unregisterSpec = useCallback((type) => {
    setRegisteredSpecs((prev) => {
      if (!(type in prev)) return prev;
      const next = { ...prev };
      delete next[type];
      return next;
    });
  }, []);

  const getRegisteredSpec = useCallback(
    (type) => registeredSpecs[type] ?? null,
    [registeredSpecs],
  );

  return { registeredSpecs, registerSpec, unregisterSpec, getRegisteredSpec };
}
