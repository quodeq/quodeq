import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';
import { sharedListVerifiedFindings } from '../../../api/shared.js';

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

/**
 * @param {{ project: string, source?: 'local'|'shared', children: React.ReactNode }} props
 *
 * Shared projects have no mutation routes on the backend (unverify is
 * local-only by design, same as dismiss/restore/delete) and the same project
 * id can exist in both worlds. When `source` is 'shared', the badge list
 * reads from the shared-repo mirror endpoint and `unverify` is a
 * defense-in-depth no-op — it never calls the local unverify endpoint, even
 * if a click handler somehow slips through.
 */
export function VerifiedFindingsProvider({ project, source = 'local', children }) {
  const [entries, setEntries] = useState([]);
  const isShared = source === 'shared';

  const refresh = useCallback(() => {
    if (!project) { setEntries([]); return; }
    const fetchVerified = isShared ? sharedListVerifiedFindings : listVerifiedFindings;
    fetchVerified(project).then(setEntries).catch(() => setEntries([]));
  }, [project, isShared]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const handler = (event) => {
      if (event.detail?.actionType === 'verify_finding') refresh();
    };
    window.addEventListener('quodeq:assistant-action-applied', handler);
    return () => window.removeEventListener('quodeq:assistant-action-applied', handler);
  }, [refresh]);

  const value = useMemo(() => {
    const notes = new Map(entries.map((e) => [keyOf(e), e.note || '']));
    return {
      keys: new Set(notes.keys()),
      noteFor: (key) => notes.get(key) || '',
      unverify: async (v) => {
        if (isShared) return;
        await unverifyFinding(project, { req: v.req, file: v.file, line: v.line });
        setEntries((prev) => prev.filter((e) => keyOf(e) !== keyOf(v)));
      },
      refresh,
    };
  }, [entries, project, refresh, isShared]);

  return (
    <VerifiedFindingsContext.Provider value={value}>
      {children}
    </VerifiedFindingsContext.Provider>
  );
}
