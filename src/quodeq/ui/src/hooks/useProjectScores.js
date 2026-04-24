/**
 * useProjectScores -- single hook for all score data.
 *
 * Fetches from the unified /scores endpoint which returns pre-rescored data.
 * No client-side rescore calls. One source of truth consumed by Overview,
 * History, Explorer, etc.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getProjectScores } from '../api/index.js';

const REFRESH_DEBOUNCE_MS = 300;

// Cache by (project, asOf) to avoid refetching on view changes.
// Cleared by clearScoresCache() when mutations happen (dismiss/restore).
const MAX_CACHE_SIZE = 100;
const _cache = new Map();
function _cacheKey(project, asOf) { return `${project}\0${asOf || 'all'}`; }

export function clearScoresCache(project) {
  if (project) {
    for (const key of [..._cache.keys()]) {
      if (key.startsWith(project + '\0')) _cache.delete(key);
    }
  } else {
    _cache.clear();
  }
}

/**
 * @param {{ selectedProject: string, selectedRun: string }} opts
 * @returns {{
 *   scores: { accumulated: Object, trend: Array, availableRuns: Array } | null,
 *   latestScores: { accumulated: Object, trend: Array, availableRuns: Array } | null,
 *   loading: boolean,
 *   error: string | null,
 *   availableRuns: Array,
 *   refreshScores: () => void,
 * }}
 */
function fetchRunScoresEffect(selectedProject, selectedRun, setScores, setLoading, setError) {
  if (!selectedProject) { setScores(null); setError(null); return; }
  const asOf = selectedRun && selectedRun !== 'latest' ? selectedRun : null;
  const key = _cacheKey(selectedProject, asOf);
  const cached = _cache.get(key);
  if (cached) {
    setScores(cached);
    setLoading(false);
    return;
  }

  let active = true;
  setLoading(true);
  getProjectScores(selectedProject, asOf)
    .then((data) => {
      if (!active) return;
      if (_cache.size >= MAX_CACHE_SIZE) _cache.delete(_cache.keys().next().value);
      _cache.set(key, data);
      setScores(data);
    })
    .catch(() => { if (active) setError('Failed to load score data. Check your connection and try refreshing.'); })
    .finally(() => { if (active) setLoading(false); });
  return () => { active = false; };
}

function fetchLatestScoresEffect(selectedProject, setLatestScores) {
  if (!selectedProject) { setLatestScores(null); return; }
  const key = _cacheKey(selectedProject, null);
  const cached = _cache.get(key);
  if (cached) {
    setLatestScores(cached);
    return;
  }

  let active = true;
  getProjectScores(selectedProject)
    .then((data) => {
      if (!active) return;
      if (_cache.size >= MAX_CACHE_SIZE) _cache.delete(_cache.keys().next().value);
      _cache.set(key, data);
      setLatestScores(data);
    })
    .catch(() => {}); // non-fatal for latest
  return () => { active = false; };
}

function syncScoresOnChange(prevProjectRef, prevRunRef, selectedProject, selectedRun, setScores, setLatestScores, setError) {
  if (prevProjectRef.current !== selectedProject) {
    prevProjectRef.current = selectedProject;
    prevRunRef.current = selectedRun;
    setScores(null);
    setLatestScores(null);
    setError(null);
  } else if (prevRunRef.current !== selectedRun) {
    prevRunRef.current = selectedRun;
    const asOf = selectedRun && selectedRun !== 'latest' ? selectedRun : null;
    const cached = _cache.get(_cacheKey(selectedProject, asOf));
    if (cached) setScores(cached);
  }
}

export function useProjectScores({ selectedProject, selectedRun }) {
  const [scores, setScores] = useState(null);
  const [latestScores, setLatestScores] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const prevProjectRef = useRef(selectedProject);
  const prevRunRef = useRef(selectedRun);
  syncScoresOnChange(prevProjectRef, prevRunRef, selectedProject, selectedRun, setScores, setLatestScores, setError);

  useEffect(() => {
    return fetchRunScoresEffect(selectedProject, selectedRun, setScores, setLoading, setError);
  }, [selectedProject, selectedRun, refreshKey]);

  useEffect(() => {
    return fetchLatestScoresEffect(selectedProject, setLatestScores);
  }, [selectedProject, refreshKey]);

  const availableRuns = useMemo(() => {
    // Prefer availableRuns from the scores payload (includes in_progress runs not in trend).
    // Fall back to deriving from trend entries (which only contain completed runs).
    const fromPayload = scores?.availableRuns || latestScores?.availableRuns;
    if (fromPayload && fromPayload.length > 0) return fromPayload;
    const trend = scores?.trend || latestScores?.trend || [];
    if (trend.length === 0) return [];
    return trend.map((row) => ({ runId: row.runId, dateLabel: row.dateLabel || row.runId, status: 'complete' }));
  }, [scores, latestScores]);

  const refreshTimerRef = useRef(null);
  const refreshScores = useCallback(() => {
    clearScoresCache(selectedProject);
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), REFRESH_DEBOUNCE_MS);
  }, [selectedProject]);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  return { scores, latestScores, loading, error, availableRuns, refreshScores };
}
