import { useEffect, useMemo, useState } from 'react';
import { getDashboard, getAccumulated } from '../../../api/index.js';

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
      if (active) setDashboard(payload);
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

  useEffect(() => fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError), [selectedProject, selectedRun]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError), [selectedProject, selectedRun]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, 'latest', setLatestAccumulated, setError), [selectedProject]);
  const availableRuns = useMemo(() => buildAvailableRuns(dashboard), [dashboard]);

  return { dashboard, accumulated, latestAccumulated, loading, error, availableRuns };
}
