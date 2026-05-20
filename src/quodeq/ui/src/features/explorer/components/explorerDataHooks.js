import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';

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
  const counts = { critical: 0, major: 0, minor: 0 };
  allViolations.forEach((v) => {
    const s = (v.severity || 'minor').toLowerCase();
    if (counts[s] !== undefined) counts[s]++;
  });
  return counts;
}

function computeComplianceByPrinciple(evalData) {
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

async function fetchAndRescore(project, runId, dimension, getDimensionEval, getRunScores) {
  const [data, rescored] = await Promise.all([
    getDimensionEval(project, runId, dimension),
    getRunScores(project, runId).catch(() => null),
  ]);
  if (rescored) {
    const dimData = (rescored.dimensions || []).find((d) => d.dimension === dimension);
    return dimData ? mergeRescoreIntoEval(data, dimData) : data;
  }
  return data;
}

export function useExplorerData(project, dimension, runId, refreshSignal) {
  const { getDimensionEval, getRunScores } = useApi();
  const [evalData, setEvalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // First load shows the LoadingScreen; subsequent run-switches keep
    // the previous run's data on screen and toggle isFetching so the
    // caller can dim the page during the background refetch (matches
    // the Overview placeholderData behaviour).
    setIsFetching(true);
    fetchAndRescore(project, runId, dimension, getDimensionEval, getRunScores)
      .then((data) => { setEvalData(data); setLoading(false); setIsFetching(false); })
      .catch((err) => { setError(err.message); setLoading(false); setIsFetching(false); });
  }, [project, dimension, runId, getDimensionEval, getRunScores]);

  const initialRef = useRef(refreshSignal);
  useEffect(() => {
    if (refreshSignal === initialRef.current) return;
    if (!evalData || !project || !runId) return;
    getRunScores(project, runId).then((rescored) => {
      const dimData = (rescored.dimensions || []).find((d) => d.dimension === dimension);
      if (dimData) setEvalData((prev) => mergeRescoreIntoEval(prev, dimData));
    }).catch(() => {});
  }, [refreshSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live updates after a dismiss arrive synchronously in the dismiss HTTP
  // response. Callers fold the rescored payload back into this hook via
  // ``applyRescoredPayload`` so the page re-renders with the new scores
  // without a follow-up GET. (Previously this was an SSE subscription, which
  // turned out to be broken for completed runs — see the long-form
  // commit message for the architectural history.)
  const applyRescoredPayload = useCallback((payload) => {
    if (!payload) return;
    const dimData = (payload.dimensions || []).find((d) => d.dimension === dimension);
    if (!dimData) return;
    setEvalData((prev) => mergeRescoreIntoEval(prev, dimData));
  }, [dimension]);

  const overallGrade = useMemo(() => (evalData?.principleGrades || []).find((pg) => pg.isOverall || pg.principle?.includes('Overall')), [evalData]);
  const principleGrades = useMemo(() => (evalData?.principleGrades || []).filter((pg) => !pg.isOverall && !pg.principle?.includes('Overall')), [evalData]);
  const allViolations = useMemo(() => computeAllViolations(evalData), [evalData]);
  const stats = useDerivedExplorerStats(evalData, allViolations);
  return {
    evalData, loading, isFetching, error,
    overallGrade, principleGrades, allViolations,
    applyRescoredPayload,
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
