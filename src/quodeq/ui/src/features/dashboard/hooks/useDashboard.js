import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getDashboard, getAccumulated, getRescore } from '../../../api/index.js';
import { createDimension } from '../../../models/dimension.js';

/**
 * Fetches and manages dashboard data for a given project and run.
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
      // Rescore dashboard dimensions for the selected run
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

/**
 * Rescore all unique runs from accumulated dimensions and build a lookup
 * of dimension name → rescored data. Stored as separate state so patching
 * accumulated doesn't cause re-render loops.
 */
function rescoreAllRunsEffect(project, accumulated, setRescoreLookup) {
  if (!project || !accumulated?.dimensions) return;
  // Map each dimension to its authoritative run (the run the accumulated view selected)
  const dimToRun = {};
  for (const d of accumulated.dimensions) {
    const key = (d.dimension || '').toLowerCase();
    const rid = d.fromRunId || d.runId;
    if (key && rid) dimToRun[key] = rid;
  }
  const runIds = [...new Set(Object.values(dimToRun))];
  if (runIds.length === 0) return;

  let active = true;
  Promise.all(runIds.map((rid) => getRescore(project, rid).then((r) => ({ rid, data: r })).catch(() => null)))
    .then((results) => {
      if (!active) return;
      const lookup = {};
      for (const r of results) {
        if (!r?.data) continue;
        for (const d of (r.data.dimensions || [])) {
          const key = (d.dimension || '').toLowerCase();
          // Only use this dimension if it came from its authoritative run
          if (dimToRun[key] === r.rid) {
            lookup[key] = d;
          }
        }
      }
      setRescoreLookup(lookup);
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
  const [rescoreLookup, setRescoreLookup] = useState({});

  // Clear stale data immediately when project changes to prevent rendering old data for a new project
  const prevProjectRef = useRef(selectedProject);
  if (prevProjectRef.current !== selectedProject) {
    prevProjectRef.current = selectedProject;
    setDashboard(null);
    setAccumulated(null);
    setLatestAccumulated(null);
    setRescoreLookup({});
    setError(null);
  }

  useEffect(() => fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, 'latest', setLatestAccumulated, setError), [selectedProject, refreshKey]);
  // Rescore all runs that contribute to accumulated — stored as lookup, not patched into accumulated
  useEffect(() => rescoreAllRunsEffect(selectedProject, accumulated, setRescoreLookup), [selectedProject, accumulated]);
  const availableRuns = useMemo(() => buildAvailableRuns(dashboard), [dashboard]);

  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), 300);
  }, []);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  return { dashboard, accumulated, latestAccumulated, rescoreLookup, loading, error, availableRuns, refreshDashboard };
}
