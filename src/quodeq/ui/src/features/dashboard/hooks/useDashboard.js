import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getDashboard, getAccumulated, getRescore } from '../../../api/index.js';
import { createDimension } from '../../../models/dimension.js';

const REFRESH_DEBOUNCE_MS = 300;

function dimKey(d) { return (d.dimension || '').toLowerCase(); }

/** Rescore multiple runs in parallel, returning { [runId]: rescoreData } */
async function fetchRescores(project, runIds) {
  const results = await Promise.all(
    runIds.map(rid => getRescore(project, rid).then(r => ({ rid, ...r })).catch(() => null))
  );
  const byRun = {};
  for (const r of results) { if (r) byRun[r.rid] = r; }
  return byRun;
}

function fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError) {
  if (!selectedProject) { setDashboard(null); setError(null); return; }

  let active = true;
  setError(null);

  getDashboard(selectedProject, selectedRun)
    .then(async (payload) => {
      if (!active) return;
      const runId = payload?.selectedRun?.runId || selectedRun;
      let dimensions = payload.dimensions;
      let summary = payload.summary;
      try {
        const rescored = await getRescore(selectedProject, runId);
        if (!active) return;
        dimensions = (rescored.dimensions || []).map(createDimension);
        summary = { ...payload.summary, ...rescored.summary };
      } catch { /* non-fatal */ }
      if (active) setDashboard(prev => ({ ...payload, dimensions, summary, trend: prev?.trend || payload.trend }));
    })
    .catch(() => { if (active) setError('Failed to load dashboard data.'); })
    .finally(() => { if (active) setLoading(false); });

  return () => { active = false; };
}

function fetchTrendEffect(selectedProject, setDashboard) {
  if (!selectedProject) return;
  let active = true;

  getDashboard(selectedProject, 'latest')
    .then(async (payload) => {
      if (!active) return;
      const trend = payload.trend || [];
      const runIds = [...new Set(trend.map(t => t.runId).filter(Boolean))];
      if (runIds.length === 0) { if (active) setDashboard(prev => ({ ...prev, trend })); return; }
      try {
        const byRun = await fetchRescores(selectedProject, runIds);
        if (!active) return;
        const rescoredTrend = trend.map(t => {
          const r = byRun[t.runId];
          if (!r) return t;
          const dl = {};
          for (const d of (r.dimensions || [])) dl[dimKey(d)] = d;
          const details = (t.dimensionDetails || []).map(dd => {
            const rd = dl[dimKey(dd)];
            if (!rd) return dd;
            return {
              ...dd,
              score: rd.overallScore ? parseFloat(rd.overallScore) : dd.score,
              overallGrade: rd.overallGrade || dd.overallGrade,
            };
          });
          return {
            ...t,
            dimensionDetails: details,
            numericAverage: r.summary?.numericAverage ?? t.numericAverage,
            runNumericAverage: r.summary?.numericAverage ?? t.runNumericAverage,
            overallGrade: r.summary?.overallGrade ?? t.overallGrade,
            runOverallGrade: r.summary?.overallGrade ?? t.runOverallGrade,
          };
        });
        if (active) setDashboard(prev => ({ ...prev, trend: rescoredTrend }));
      } catch {
        if (active) setDashboard(prev => ({ ...prev, trend }));
      }
    })
    .catch(() => {});

  return () => { active = false; };
}

function fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError, rescore = false) {
  if (!selectedProject) { setAccumulated(null); return; }

  let active = true;
  const asOf = selectedRun && selectedRun !== 'latest' ? selectedRun : null;

  getAccumulated(selectedProject, asOf)
    .then(async (data) => {
      if (!active) return;
      let patched = data;
      if (rescore && data?.dimensions?.length > 0) {
        try {
          // Group runs by source project — parent dimensions may reference child projects
          const runsByProject = {};
          for (const d of data.dimensions) {
            const proj = d.fromProject || selectedProject;
            const rid = d.fromRunId || d.runId;
            if (rid) {
              if (!runsByProject[proj]) runsByProject[proj] = new Set();
              runsByProject[proj].add(rid);
            }
          }
          const lookup = {};
          for (const [proj, rids] of Object.entries(runsByProject)) {
            const byRun = await fetchRescores(proj, [...rids]);
            if (!active) return;
            for (const [, r] of Object.entries(byRun)) {
              for (const d of (r.dimensions || []).map(createDimension)) {
                lookup[dimKey(d)] = d;
              }
            }
          }
          patched = {
            ...data,
            dimensions: data.dimensions.map(dim => {
              const rescored = lookup[dimKey(dim)];
              return rescored ? { ...dim, ...rescored } : dim;
            }),
          };
        } catch { /* non-fatal */ }
      }
      if (active) setAccumulated(patched);
    })
    .catch((err) => {
      console.error('Dashboard load failed:', err);
      if (active) setError('Failed to load accumulated data');
    });

  return () => { active = false; };
}

function rescoreAllRunsEffect(project, accumulated, setRescoreLookup) {
  if (!project || !accumulated?.dimensions) return;
  const dimToRun = {};
  for (const d of accumulated.dimensions) {
    const key = dimKey(d);
    const rid = d.fromRunId || d.runId;
    if (key && rid) dimToRun[key] = rid;
  }
  const runIds = [...new Set(Object.values(dimToRun))];
  if (runIds.length === 0) return;

  let active = true;
  fetchRescores(project, runIds)
    .then((byRun) => {
      if (!active) return;
      const lookup = {};
      for (const [rid, r] of Object.entries(byRun)) {
        for (const d of (r.dimensions || [])) {
          const key = dimKey(d);
          if (dimToRun[key] === rid) lookup[key] = d;
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

  // Clear stale data immediately when project or run changes to prevent rendering old data
  const prevProjectRef = useRef(selectedProject);
  const prevRunRef = useRef(selectedRun);
  if (prevProjectRef.current !== selectedProject) {
    prevProjectRef.current = selectedProject;
    prevRunRef.current = selectedRun;
    setDashboard(null);
    setAccumulated(null);
    setLatestAccumulated(null);
    setRescoreLookup({});
    setError(null);
  } else if (prevRunRef.current !== selectedRun) {
    prevRunRef.current = selectedRun;
    // Clear run-specific dimensions, trend stays stable
    setDashboard((prev) => prev ? { trend: prev.trend } : null);
  }

  // Trend: loads once per project, rescored once — stable across run changes
  useEffect(() => fetchTrendEffect(selectedProject, setDashboard), [selectedProject, refreshKey]);
  // Dashboard (dimensions/summary): loads per run
  useEffect(() => { setLoading(true); return fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError); }, [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, selectedRun, setAccumulated, setError, true), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => fetchAccumulatedEffect(selectedProject, 'latest', setLatestAccumulated, setError, true), [selectedProject, selectedRun, refreshKey]);
  useEffect(() => rescoreAllRunsEffect(selectedProject, accumulated, setRescoreLookup), [selectedProject, accumulated]);
  const availableRuns = useMemo(() => buildAvailableRuns(dashboard), [dashboard]);

  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), REFRESH_DEBOUNCE_MS);
  }, []);

  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);

  return { dashboard, accumulated, latestAccumulated, rescoreLookup, loading, error, availableRuns, refreshDashboard };
}
