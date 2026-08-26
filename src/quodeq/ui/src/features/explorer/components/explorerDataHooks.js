import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectKeys, samePlaceholderScope } from '../../../api/queryKeys.js';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';
import { countBySeverity } from '../../../utils/severity.js';

export function computeAllViolations(evalData) {
  if (!evalData) return [];
  if (evalData.violations?.length > 0) return evalData.violations;
  return (evalData.principles || []).flatMap((p) =>
    (p.violations || []).map((v) => ({
      principle: p.name,
      file: v.file ? v.file.split(':')[0] : null,
      line: v.line || null,
      severity: v.severity || 'minor',
      reason: v.reason || v.code || '',
    }))
  );
}

export function computeSeverityCounts(allViolations) {
  return countBySeverity(allViolations);
}

export function computeComplianceByPrinciple(evalData) {
  const map = new Map();
  for (const c of (evalData?.compliance || [])) {
    if (!map.has(c.principle)) map.set(c.principle, []);
    map.get(c.principle).push(c);
  }
  return map;
}

export function buildEvalPrincipalFn(evalData, complianceByPrinciple, project, runId, dateLabel = '') {
  const principlesByName = new Map((evalData.principles || []).map((p) => [p.name, p]));
  const gradesByPrinciple = new Map((evalData.principleGrades || []).map((p) => [p.principle, p]));
  return function buildEvalPrincipal(principleId) {
    const principleData = principlesByName.get(principleId);
    const pg = gradesByPrinciple.get(principleId);
    return {
      principle: principleId, score: pg?.score || null, grade: pg?.grade || null,
      dimension: evalData.dimension || '',
      project: project || '', runId: runId || '', dateLabel: dateLabel || '',
      principleData, dimViolations: principleData?.violations || [],
      dimCompliance: complianceByPrinciple.get(principleId) || [],
    };
  };
}

function useDerivedExplorerStats(evalData, allViolations) {
  const topFiles = useMemo(() => evalData ? buildTopOffendingFiles([{ dimension: evalData.dimension, violations: allViolations }]) : [], [evalData, allViolations]);
  const severityCounts = useMemo(() => computeSeverityCounts(allViolations), [allViolations]);
  const uniquePrinciples = useMemo(() => new Set(allViolations.map((v) => v.principle).filter(Boolean)).size, [allViolations]);
  const totalCompliant = useMemo(() => (evalData?.principles || []).reduce((sum, p) => sum + (p.compliance?.length || 0), 0), [evalData]);
  const complianceByPrinciple = useMemo(() => computeComplianceByPrinciple(evalData), [evalData]);
  return { topFiles, severityCounts, uniquePrinciples, totalCompliant, complianceByPrinciple };
}

function mergeRescoreIntoEval(prev, dimData) {
  if (!prev || !dimData) return prev;
  const rescPrinciples = dimData.principles || [];
  const rescMap = new Map(rescPrinciples.map(rp => [rp.principle, rp]));
  const updatedGrades = (prev.principleGrades || []).map((pg) => {
    if (pg.isOverall || pg.principle?.includes('Overall')) {
      return { ...pg, score: dimData.overallScore ?? pg.score, grade: dimData.overallGrade ?? pg.grade };
    }
    const match = rescMap.get(pg.principle);
    return match ? { ...pg, score: match.score, grade: match.grade } : pg;
  });
  // Build set of dismissed violation keys for filtering
  const rescViolationKeys = new Set(
    (dimData.violations || []).map((v) => `${v.req || ''}|${v.file || ''}|${v.line || 0}`)
  );
  // Filter violations to only include those that survived rescore
  const filteredViolations = dimData.violations != null
    ? (prev.violations || []).filter((v) => rescViolationKeys.has(`${v.req || ''}|${v.file || ''}|${v.line || 0}`))
    : prev.violations;
  // Update totals
  const totals = dimData.totals ?? prev.totals;
  return {
    ...prev,
    violations: filteredViolations,
    principleGrades: updatedGrades,
    overallScore: dimData.overallScore ?? prev.overallScore,
    overallGrade: dimData.overallGrade ?? prev.overallGrade,
    totals,
  };
}

/**
 * @param {string} project
 * @param {string} dimension
 * @param {string} runId
 * @param {*} refreshSignal
 * @param {'local'|'shared'} [selectedSource='local'] - picks the shared-repo
 *   mirror fetchers (sharedGetDimensionEval/sharedGetRunScores) instead of
 *   the local ones when the selected project is a shared-repo project.
 *
 * Both queries live in the react-query cache under the project subtree, so
 * re-entering the page (Back from a principle/file detail) renders instantly
 * from cache instead of refetching behind a full-screen LoadingScreen — the
 * cost that used to make every Back out of a principle a multi-second hop.
 * Every dismiss/delete/formula mutation already invalidates the
 * projectKeys.project() prefix (see refreshDashboard/scheduleDashboardReconcile
 * in useDashboard.js), which marks these stale too, so the cached page
 * refetches after user actions exactly like the Overview does.
 */
export function useExplorerData(project, dimension, runId, refreshSignal, selectedSource = 'local') {
  const { getDimensionEval, getRunScores, sharedGetDimensionEval, sharedGetRunScores } = useApi();
  const fetchDimensionEval = selectedSource === 'shared' ? sharedGetDimensionEval : getDimensionEval;
  const fetchRunScores = selectedSource === 'shared' ? sharedGetRunScores : getRunScores;
  const queryClient = useQueryClient();
  const projectKey = project || '_none_';
  // Reuse the previous payload only within this project+source subtree —
  // run-navigator swaps keep the page up with an isFetching dim, a project
  // switch drops to the real LoadingScreen (see samePlaceholderScope).
  const keepInScope = useCallback(
    (prev, prevQuery) => (samePlaceholderScope(prevQuery, projectKey, selectedSource) ? prev : undefined),
    [projectKey, selectedSource],
  );

  const evalQuery = useQuery({
    queryKey: projectKeys.dimensionEval(projectKey, runId, dimension, selectedSource),
    queryFn: () => fetchDimensionEval(project, runId, dimension),
    enabled: !!project && !!dimension,
    staleTime: 60_000,
    placeholderData: keepInScope,
  });

  // The rescore side. Non-fatal by design: if it errors, the page renders
  // the unrescored eval (the old fetchAndRescore caught and dropped scores
  // errors the same way).
  const scoresQuery = useQuery({
    queryKey: projectKeys.runScores(projectKey, runId, selectedSource),
    queryFn: () => fetchRunScores(project, runId),
    enabled: !!project,
    staleTime: 60_000,
    placeholderData: keepInScope,
  });

  const evalData = useMemo(() => {
    const data = evalQuery.data ?? null;
    if (!data) return null;
    const dimData = (scoresQuery.data?.dimensions || []).find((d) => d.dimension === dimension);
    return dimData ? mergeRescoreIntoEval(data, dimData) : data;
  }, [evalQuery.data, scoresQuery.data, dimension]);

  // refreshSignal (the dashboard payload identity) flips after external
  // changes; re-pull the rescore data then, like the old effect did.
  const initialRef = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal === initialRef.current) return;
    if (!project || !runId) return;
    queryClient.invalidateQueries({ queryKey: projectKeys.runScores(projectKey, runId, selectedSource) });
  }, [refreshSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  // Loading gates on BOTH queries so the first paint never shows pre-rescore
  // grades that visibly correct themselves a beat later (the old code
  // Promise.all'd the two fetches for the same reason). isLoading is false
  // once cached data exists, so Back-navigation skips the LoadingScreen.
  const loading = evalQuery.isLoading || scoresQuery.isLoading;
  const isFetching = evalQuery.isFetching || scoresQuery.isFetching;
  const error = evalQuery.isError ? (evalQuery.error?.message || String(evalQuery.error)) : null;

  const overallGrade = useMemo(() => (evalData?.principleGrades || []).find((pg) => pg.isOverall || pg.principle?.includes('Overall')), [evalData]);
  const principleGrades = useMemo(() => (evalData?.principleGrades || []).filter((pg) => !pg.isOverall && !pg.principle?.includes('Overall')), [evalData]);
  const allViolations = useMemo(() => computeAllViolations(evalData), [evalData]);
  const stats = useDerivedExplorerStats(evalData, allViolations);
  return {
    evalData, loading, isFetching, error,
    // 202 sentinel: the run dir exists but evaluation/<dim>.json isn't
    // written (yet). Callers must not render this as a real, zero-finding
    // report.
    waiting: !!evalData?.waiting,
    overallGrade, principleGrades, allViolations,
    ...stats,
  };
}

/**
 * Manages per-principle local state for PrincipleDetailPage: dismissed
 * violations and the post-dismiss live score/grade.
 *
 * The dismiss handler is async and resolves to ``{ scores }`` returned by
 * the backend. This hook folds the returned principle's score/grade into
 * liveScore/liveGrade so the page reflects the change as soon as the POST
 * completes — no SSE roundtrip, no fingerprint state machine.
 *
 * @param {Object} evalPrincipal - { principle, dimension, project, runId, ... }
 * @param {string|null} severityFilter - initial severity filter
 * @param {Function|null} onDismiss - async ``(v) => { scores }``. Returning
 *   ``null`` or missing ``scores`` leaves the page at its initial score
 *   (callers should also call refreshDashboard for the cross-run rollup).
 * @returns {{ liveScore, liveGrade, activeSevFilter, setActiveSevFilter, handleDismiss, dismissedSet }}
 */
export function usePrincipleData(evalPrincipal, severityFilter, onDismiss) {
  const { principle, dimension } = evalPrincipal;
  const [dismissedSet, setDismissedSet] = useState(new Set());
  const [liveScore, setLiveScore] = useState(null);
  const [liveGrade, setLiveGrade] = useState(null);
  const [activeSevFilter, setActiveSevFilter] = useState(severityFilter || null);

  const handleDismiss = useCallback(async (v) => {
    if (!onDismiss) return;
    // Optimistic local removal so the violation disappears immediately.
    setDismissedSet((prev) => new Set(prev).add(`${v.file}:${v.line}`));
    try {
      const result = await onDismiss(v);
      const scores = result?.scores;
      if (!scores) return;
      const dimData = (scores.dimensions || []).find((d) => d.dimension === dimension);
      const pg = dimData?.principles?.find((p) => p.principle === principle);
      if (pg) {
        setLiveScore(pg.score);
        setLiveGrade(pg.grade);
      }
    } catch (err) {
      // Roll back the optimistic update so the violation re-appears.
      setDismissedSet((prev) => {
        const next = new Set(prev);
        next.delete(`${v.file}:${v.line}`);
        return next;
      });
      // eslint-disable-next-line no-console
      console.error('[usePrincipleData] dismiss failed:', err);
    }
  }, [onDismiss, dimension, principle]);

  return { liveScore, liveGrade, activeSevFilter, setActiveSevFilter, handleDismiss, dismissedSet };
}
