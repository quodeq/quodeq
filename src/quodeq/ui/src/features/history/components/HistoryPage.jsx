import { useState, useMemo } from 'react';
import HistoryRunRow from './HistoryRunRow.jsx';
import HistoryChartPanel from './HistoryChartPanel.jsx';

import RunNavigator from '../../dashboard/components/RunNavigator.jsx';
import { useRunNavigator } from '../../../hooks/useRunNavigator.js';
import { readVisibleStandardIds } from '../../../utils/visibleStandards.js';

const MAX_VISIBLE = 20;

function roundOneDecimal(n) {
  return Math.round(n * 10) / 10;
}

/**
 * Recompute accumulated and run averages using only visible dimensions,
 * applying rescored values when available to match the Overview score circle.
 */
function filterTrendByVisibleStandards(trend, visibleSet, rescoreLookup) {
  const accByDim = {};
  const reversed = [...trend].reverse(); // oldest first
  const filtered = [];
  for (const entry of reversed) {
    for (const d of (entry.dimensionDetails || [])) {
      const dimId = (d.dimension || '').toLowerCase();
      if (visibleSet.has(dimId) && d.score != null) {
        const rescored = rescoreLookup[dimId];
        accByDim[dimId] = rescored ? parseFloat(rescored.overallScore) || d.score : d.score;
      }
    }
    const accScores = Object.values(accByDim).filter((s) => s != null && !isNaN(s));
    const accAvg = accScores.length > 0 ? roundOneDecimal(accScores.reduce((a, b) => a + b, 0) / accScores.length) : null;
    const visibleDetails = (entry.dimensionDetails || []).filter((d) => visibleSet.has((d.dimension || '').toLowerCase()));
    const runScores = visibleDetails.map((d) => {
      const dimId = (d.dimension || '').toLowerCase();
      const rescored = rescoreLookup[dimId];
      return rescored ? parseFloat(rescored.overallScore) || d.score : d.score;
    }).filter((s) => s != null && !isNaN(s));
    const runAvg = runScores.length > 0 ? roundOneDecimal(runScores.reduce((a, b) => a + b, 0) / runScores.length) : null;
    filtered.push({ ...entry, numericAverage: accAvg, runNumericAverage: runAvg, dimensionDetails: visibleDetails });
  }
  filtered.reverse();
  return filtered;
}

function computeDeltas(trend) {
  return trend.map((entry, i) => {
    if (i >= trend.length - 1) return null;
    const curr = parseFloat(entry.numericAverage);
    const prev = parseFloat(trend[i + 1].numericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return Math.round((curr - prev) * 10) / 10;
  });
}

function HistoryEmpty() {
  return (
    <div className="history-page">
      <div className="page-header">
        <h2 className="page-title">History</h2>
      </div>
      <div className="empty-state">
        <p>No evaluations yet. Run one from the Evaluate tab.</p>
      </div>
    </div>
  );
}

function HistoryContent({ data, callbacks, showAll, setShowAll, runNav }) {
  const { trend, selectedRunId, availableRuns } = data;
  const { onRunClick, onRunChange } = callbacks;
  const { runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = runNav;
  const deltas = computeDeltas(trend);
  const visible = showAll ? trend : trend.slice(0, MAX_VISIBLE);
  const hasMore = trend.length > MAX_VISIBLE && !showAll;

  return (
    <div className="history-page">
      <div className="page-header">
        <h2 className="page-title">History</h2>
        <span className="page-count">{trend.length} evaluation{trend.length !== 1 ? 's' : ''}</span>
        {availableRuns && availableRuns.length > 0 && (
          <div className="history-run-nav">
            <RunNavigator currentRun={runNavLabel} isLatest={overviewRunIndex === 0} isOldest={overviewRunIndex >= availableRuns.length - 1} actions={{ onPrev: handleRunPrev, onNext: handleRunNext, onLatest: handleRunLatest, onView: () => { if (currentOverviewRun) onRunClick(currentOverviewRun); } }} />
          </div>
        )}
      </div>
      <HistoryChartPanel trend={trend} selectedRunId={selectedRunId} onBarClick={(runId) => onRunChange(runId)} />
      <div className="section-header"><h3 className="section-title">Evaluations</h3></div>
      <div className="history-list">
        {visible.map((entry, i) => (
          <HistoryRunRow key={entry.runId} entry={entry} delta={deltas[i]} isSelected={entry.runId === selectedRunId} onClick={onRunClick} />
        ))}
      </div>
      {hasMore && (
        <div className="history-load-more">
          <button type="button" className="history-load-more-btn" onClick={() => setShowAll(true)}>Load all {trend.length} evaluations</button>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage({ trend: rawTrend, rescoreLookup, selection, availableRuns, dimensions, callbacks }) {
  const { selectedRunId } = selection;
  const { onRunClick, onDimensionClick, onNavigate, onRunChange } = callbacks;
  const [showAll, setShowAll] = useState(false);
  const visibleSet = useMemo(() => new Set(readVisibleStandardIds()), []);
  const trend = useMemo(() => filterTrendByVisibleStandards(rawTrend || [], visibleSet, rescoreLookup || {}), [rawTrend, visibleSet, rescoreLookup]);

  const { overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest } = useRunNavigator({
    selectedRun: selectedRunId || 'latest',
    availableRuns: availableRuns || [],
    onRunChange: onRunChange || (() => {}),
    onNavigate: onNavigate || (() => {}),
  });

  const runNavLabel = useMemo(() => {
    const entry = (trend || []).find((r) => r.runId === currentOverviewRun);
    if (entry?.dateISO) {
      try {
        const d = new Date(entry.dateISO);
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      } catch { return entry.dateISO || ''; }
    }
    return entry?.dateLabel || currentOverviewRun;
  }, [trend, currentOverviewRun]);

  if (!trend || trend.length === 0) return <HistoryEmpty />;

  return (
    <HistoryContent
      data={{ trend, selectedRunId, availableRuns }}
      callbacks={{ onRunClick, onRunChange }}
      showAll={showAll} setShowAll={setShowAll}
      runNav={{ runNavLabel, overviewRunIndex, currentOverviewRun, handleRunPrev, handleRunNext, handleRunLatest }}
    />
  );
}
