import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';

/**
 * Project-level verified-badge state. Findings are keyed by
 * `${req}|${file}|${line}` (the same convention the dismissal paths use).
 * Consumers get null when no provider is mounted, so cards render without
 * badges in isolated tests and legacy mounts.
 */
const VerifiedFindingsContext = createContext(null);

export function useVerifiedFindings() {
  return useContext(VerifiedFindingsContext);
}

const keyOf = (v) => `${v.req || ''}|${v.file || ''}|${v.line || 0}`;

export function VerifiedFindingsProvider({ project, children }) {
  const [entries, setEntries] = useState([]);

  const refresh = useCallback(() => {
    if (!project) { setEntries([]); return; }
    listVerifiedFindings(project).then(setEntries).catch(() => setEntries([]));
  }, [project]);

  useEffect(() => { refresh(); }, [refresh]);

  const value = useMemo(() => {
    const notes = new Map(entries.map((e) => [keyOf(e), e.note || '']));
    return {
      keys: new Set(notes.keys()),
      noteFor: (key) => notes.get(key) || '',
      unverify: async (v) => {
        await unverifyFinding(project, { req: v.req, file: v.file, line: v.line });
        setEntries((prev) => prev.filter((e) => keyOf(e) !== keyOf(v)));
      },
      refresh,
    };
  }, [entries, project, refresh]);

  return (
    <VerifiedFindingsContext.Provider value={value}>
      {children}
    </VerifiedFindingsContext.Provider>
  );
}
