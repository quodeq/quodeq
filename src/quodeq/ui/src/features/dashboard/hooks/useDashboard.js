import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getDashboard } from '../../../api/index.js';
import { useProjectScores, clearScoresCache } from '../../../hooks/useProjectScores.js';

const REFRESH_DEBOUNCE_MS = 300;

// Run data cache — only for the per-run dashboard view (dimensions/summary).
// The unified scores endpoint handles accumulated + rescore + trend.
// Shared mutable state; use clearDashboardCache() for test resets.
const _runCache = new Map();
function _runCacheKey(project, run) { return `${project}\0${run || 'latest'}`; }

export function clearDashboardCache(project) {
  clearScoresCache(project);
  if (project) {
    for (const key of [..._runCache.keys()]) {
      if (key.startsWith(project + '\0')) _runCache.delete(key);
    }
  } else {
    _runCache.clear();
  }
}

function fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError) {
  if (!selectedProject) { setDashboard(null); setError(null); return; }

  const cacheKey = _runCacheKey(selectedProject, selectedRun);
  const cached = _runCache.get(cacheKey);
  if (cached) {
    setDashboard(cached);
    setLoading(false);
    return undefined;
  }

  let active = true;
  setError(null);

  getDashboard(selectedProject, selectedRun)
    .then((payload) => {
      if (!active) return;
      _runCache.set(cacheKey, payload);
      if (active) setDashboard(payload);
    })
    .catch(() => { if (active) setError('Failed to load dashboard data.'); })
    .finally(() => { if (active) setLoading(false); });

  return () => { active = false; };
}

function syncProjectState(prevProjectRef, prevRunRef, selectedProject, selectedRun, setDashboard, setError) {
  if (prevProjectRef.current !== selectedProject) {
    prevProjectRef.current = selectedProject;
    prevRunRef.current = selectedRun;
    setDashboard(null);
    setError(null);
  } else if (prevRunRef.current !== selectedRun) {
    prevRunRef.current = selectedRun;
    const dashKey = _runCacheKey(selectedProject, selectedRun);
    const cachedDash = _runCache.get(dashKey);
    if (cachedDash) setDashboard(cachedDash);
  }
}

function useDebouncedRefresh(selectedProject, refreshScores, setRefreshKey) {
  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    clearDashboardCache(selectedProject);
    refreshScores();
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), REFRESH_DEBOUNCE_MS);
  }, [selectedProject, refreshScores, setRefreshKey]);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);
  return refreshDashboard;
}

export function useDashboard({ selectedProject, selectedRun }) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const { scores, latestScores, loading: scoresLoading, error: scoresError, availableRuns, refreshScores } = useProjectScores({ selectedProject, selectedRun });

  const prevProjectRef = useRef(selectedProject);
  const prevRunRef = useRef(selectedRun);
  syncProjectState(prevProjectRef, prevRunRef, selectedProject, selectedRun, setDashboard, setError);

  useEffect(() => {
    setLoading(true);
    return fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError);
  }, [selectedProject, selectedRun, refreshKey]);

  const dashboardWithTrend = useMemo(() => {
    if (!dashboard) return null;
    const trend = scores?.trend || latestScores?.trend || dashboard.trend || [];
    return { ...dashboard, trend };
  }, [dashboard, scores, latestScores]);

  const accumulated = scores?.accumulated || null;
  const latestAccumulated = latestScores?.accumulated || null;
  const refreshDashboard = useDebouncedRefresh(selectedProject, refreshScores, setRefreshKey);

  return {
    dashboard: dashboardWithTrend,
    accumulated,
    latestAccumulated,
    rescoreLookup: {},
    loading: loading || scoresLoading,
    error: error || scoresError,
    availableRuns,
    refreshDashboard,
  };
}
