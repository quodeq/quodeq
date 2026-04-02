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
function fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError) {
  if (!selectedProject) {
    setDashboard(null);
    setError(null);
    return;
  }

  let active = true;
  setLoading(true);
  setError(null);

  getDashboard(selectedProject, selectedRun)
    .then((payload) => {
      if (!active) return;
      setDashboard(payload);
      // Chain rescore to update grades with dismissed findings filtered
      // Errors are caught separately so the dashboard still shows original data
      const runId = payload?.selectedRun?.runId || selectedRun;
      getRescore(selectedProject, runId).then((rescored) => {
        if (!active) return;
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
      if (active) setError('Failed to load dashboard data. Please try again.');
    })
    .finally(() => {
      if (active) setLoading(false);
    });

  return () => { active = false; };
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
  const availableRuns = useMemo(() => buildAvailableRuns(dashboard), [dashboard]);

  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), 300);
  }, []);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  return { dashboard, accumulated, latestAccumulated, loading, error, availableRuns, refreshDashboard };
}
