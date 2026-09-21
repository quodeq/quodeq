import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getDimensionEval } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';
import {
  buildEvalPrincipalFn,
  computeComplianceByPrinciple,
} from '../../../utils/evalPrincipal.js';
import { STALE_TIME_MS } from '../../../hooks/queryDefaults.js';

// Fetch the target run's dimension eval through that project's query subtree
// (so the explorer's own cache entry is reused rather than duplicated) and
// shape it the way the principle page expects.
async function loadEvalPrincipal(queryClient, target) {
  const evalData = await queryClient.fetchQuery({
    queryKey: projectKeys.dimensionEval(target.id, target.runId, target.dimName),
    queryFn: () => getDimensionEval(target.id, target.runId, target.dimName),
    staleTime: STALE_TIME_MS,
  });
  return buildEvalPrincipalFn(
    evalData,
    computeComplianceByPrinciple(evalData),
    target.id,
    target.runId,
    target.dateLabel || '',
  )(target.principle);
}

/**
 * Open one project's own view of one principle: fetch that project's
 * dimension eval (cached in its query subtree), build the evalPrincipal with
 * the explorer's own builders, and hand it to `onOpenEvalPrincipal` — the
 * caller decides whether that's a push or a replace.
 */
export function useOpenPrinciple({ onOpenEvalPrincipal, openProject }) {
  const queryClient = useQueryClient();

  const openPrinciple = useCallback(async (target) => {
    // Remote rows can't deep-link into local project pages; opening the
    // shared project itself is the honest fallback (same degradation the
    // standings rows use).
    if (target?.remote) { openProject(target.id); return; }
    if (!onOpenEvalPrincipal || !target?.runId || !target?.dimName) return;
    try {
      onOpenEvalPrincipal(await loadEvalPrincipal(queryClient, target));
    } catch (err) {
      // Fetch failed (run pruned, server hiccup): stay on Compare rather
      // than landing on an empty principle page.
      console.warn('[useOpenPrinciple] dimension eval fetch failed:', err);
    }
  }, [onOpenEvalPrincipal, queryClient, openProject]);

  return openPrinciple;
}
