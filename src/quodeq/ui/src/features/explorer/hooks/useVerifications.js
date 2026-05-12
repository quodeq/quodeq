import { useEffect, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';

/**
 * Fetch all verifications for an evaluation and return a stable
 * `finding_id -> { verdict, confidence }` map. The API returns the rows
 * newest-first; when multiple verifications exist for the same finding,
 * the first occurrence (= newest) wins.
 *
 * @param {string|null|undefined} evalId
 * @returns {{ map: Map<string, {verdict: string, confidence: number}>, loading: boolean }}
 */
export function useVerifications(evalId) {
  const { listVerifications } = useApi();
  const [state, setState] = useState({ map: new Map(), loading: !!evalId });

  useEffect(() => {
    if (!evalId) {
      setState({ map: new Map(), loading: false });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true }));
    listVerifications(evalId)
      .then((body) => {
        if (cancelled) return;
        const map = new Map();
        for (const v of body?.verifications || []) {
          if (map.has(v.finding_id)) continue;
          map.set(v.finding_id, {
            verdict: v.verdict,
            confidence: v.confidence,
          });
        }
        setState({ map, loading: false });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ map: new Map(), loading: false });
      });
    return () => { cancelled = true; };
  }, [evalId, listVerifications]);

  return state;
}
