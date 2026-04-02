import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getDashboard, getAccumulated, getRescore } from '../../../api/index.js';
import { createDimension } from '../../../models/dimension.js';

/**
 * Fetches and manages dashboard data for a given project and run.
 *
 * @param {{ selectedProject: string, selectedRun: string }} params
 * @returns {{
 *   dashboard: object|null,
 *   accumulated: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   availableRuns: Array<{ runId: string, dateLabel: string }>,
 * }}
 */
function patchAccumulatedWithLookup(setAcc, lookup) {
  if (Object.keys(lookup).length === 0) return;
  setAcc((prev) => {
    if (!prev?.dimensions) return prev;
    const patched = prev.dimensions.map((dim) => {
      const match = lookup[(dim.dimension || '').toLowerCase()];
      if (!match) return dim;
      return { ...dim, overallScore: match.overallScore, overallGrade: match.overallGrade, totals: match.totals ?? dim.totals };
    });
    return { ...prev, dimensions: patched };
  });
}

function rescoreAccumulatedEffect(project, accumulated, setAcc) {
  if (!project || !accumulated?.dimensions) return;
  const runIds = [...new Set(accumulated.dimensions.map((d) => d.fromRunId || d.runId).filter(Boolean))];
  if (runIds.length === 0) return;

  let active = true;
  Promise.all(runIds.map((rid) => getRescore(project, rid).catch(() => null)))
    .then((results) => {
      if (!active) return;
      const lookup = {};
      for (const r of results) {
        if (!r) continue;
        for (const d of (r.dimensions || [])) {
          lookup[(d.dimension || '').toLowerCase()] = d;
        }
      }
      patchAccumulatedWithLookup(setAcc, lookup);
    });
  return () => { active = false; };
}

function fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError) {
  if (!selectedProject) {
    setDashboard(null);
    setError(null);
    return;
  }

  const activeRef = { current: true };
  setLoading(true);
  setError(null);

  getDashboard(selectedProject, selectedRun)
    .then((payload) => {
      if (!activeRef.current) return;
      setDashboard(payload);
      // Rescore dashboard dimensions for the selected run
      const runId = payload?.selectedRun?.runId || selectedRun;
      getRescore(selectedProject, runId).then((rescored) => {
        if (!activeRef.current) return;
        setDashboard((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            dimensions: (rescored.dimensions || []).map(createDimension),
            summary: { ...prev.summary, ...rescored.summary },
          };
        });
      }).catch((err) => console.warn('Rescore failed (non-fatal):', err));
    })
    .catch((err) => {
      console.warn('Dashboard load failed:', err);
      if (activeRef.current) setError('Failed to load dashboard data. Please try again.');
    })
    .finally(() => {
      if (activeRef.current) setLoading(false);
    });

  return () => { activeRef.current = false; };
}

function fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError) {
  if (!selectedProject) {
    setAccumulated(null);
    return;
  }

  let active = true;
  const asOf = selectedRun && selectedRun !== 'latest' ? selectedRun : null;

  getAccumulated(selectedProject, asOf)
    .then((data) => {
      if (active) setAccumulated(data);
    })
    .catch((err) => {
      console.error('Dashboard load failed:', err);
      if (active) setError('Failed to load accumulated data');
    });

  return () => { active = false; };
}

function buildAvailableRuns(dashboard) {
  const trendRows = dashboard?.trend || [];
  if (trendRows.length === 0) return [];
  return trendRows.map((row) => ({
    runId: row.runId,
    dateLabel: row.dateLabel || row.runId,
  }));
}

export function useDashboard({ selectedProject, selectedRun }) {
  const [dashboard, setDashboard] = useState(null);
  const [accumulated, setAccumulated] = useState(null);
  const [latestAccumulated, setLatestAccumulated] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Clear stale data immediately when project changes to prevent rendering old data for a new project
  const prevProjectRef = useRef(selectedProject);
  if (prevProjectRef.current !== selectedProject) {
    prevProjectRef.current = selectedProject;
    setDashboard(null);
    setAccumulated(null);
    setLatestAccumulated(null);
    setError(null);
  }

  useEffect(() => fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, 'latest', setLatestAccumulated, setError), [selectedProject, refreshKey]);
  // Rescore accumulated dimensions — runs after accumulated loads/refreshes
  // Uses a ref to track whether accumulated has been rescored for the current refreshKey
  const accRescoredRef = useRef(-1);
  useEffect(() => {
    if (!accumulated || accRescoredRef.current === refreshKey) return;
    accRescoredRef.current = refreshKey;
    return rescoreAccumulatedEffect(selectedProject, accumulated, setAccumulated);
  }, [accumulated, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const latestAccRescoredRef = useRef(-1);
  useEffect(() => {
    if (!latestAccumulated || latestAccRescoredRef.current === refreshKey) return;
    latestAccRescoredRef.current = refreshKey;
    return rescoreAccumulatedEffect(selectedProject, latestAccumulated, setLatestAccumulated);
  }, [latestAccumulated, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const availableRuns = useMemo(() => buildAvailableRuns(dashboard), [dashboard]);

  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), 300);
  }, []);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  return { dashboard, accumulated, latestAccumulated, loading, error, availableRuns, refreshDashboard };
}
