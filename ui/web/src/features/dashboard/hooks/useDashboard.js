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
export function useDashboard({ selectedProject, selectedRun }) {
  const [dashboard, setDashboard] = useState(null);
  const [accumulated, setAccumulated] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch dashboard whenever the project or run changes.
  useEffect(() => {
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
      .catch(() => {
        if (active) setError('Failed to load dashboard data. Please try again.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedProject, selectedRun]);

  // Fetch accumulated data whenever the project changes.
  // Uses selectedRun as the asOf boundary so the accumulated view stays
  // aligned with the currently selected run.
  useEffect(() => {
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

    return () => {
      active = false;
    };
  }, [selectedProject, selectedRun]);

  // Build the list of available runs from the trend data embedded in the
  // dashboard response (newest first, matching App.jsx overviewAvailableRuns).
  const availableRuns = useMemo(() => {
    const trendRows = dashboard?.trend || [];
    if (trendRows.length === 0) return [];
    return trendRows.map((row) => ({
      runId: row.runId,
      dateLabel: row.dateLabel || row.runId,
    }));
  }, [dashboard]);

  return { dashboard, accumulated, loading, error, availableRuns };
}
