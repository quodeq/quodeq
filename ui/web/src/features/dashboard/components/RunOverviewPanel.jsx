import { useMemo } from 'react';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { buildTopOffendingFiles, buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { formatRunId, gradeColorClass, scoreColorClass, splitScore, mostFrequentGrade } from '../../../utils/formatters.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildRunSummary(dimensions) {
  if (!dimensions || dimensions.length === 0) {
    return {
      overallGrade: '-',
      numericAverage: null,
      totalViolations: 0,
      totalCompliance: 0,
      dimensionCount: 0,
      severity: { critical: 0, major: 0, minor: 0 },
    };
  }

  const grades = dimensions.map((d) => d.overallGrade).filter(Boolean);
  const scores = dimensions.map((d) => parseFloat(d.overallScore)).filter((s) => !isNaN(s));
  const numericAverage =
    scores.length > 0
      ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      : null;

  return {
    overallGrade: mostFrequentGrade(grades) || '-',
    numericAverage,
    totalViolations: dimensions.reduce((sum, d) => sum + (d.totals?.violationCount || 0), 0),
    totalCompliance: dimensions.reduce((sum, d) => sum + (d.totals?.complianceCount || 0), 0),
    dimensionCount: dimensions.length,
    severity: {
      critical: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.critical || 0), 0),
      major: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.major || 0), 0),
      minor: dimensions.reduce((sum, d) => sum + (d.totals?.severity?.minor || 0), 0),
    },
  };
}

function withDimensionsStr(files) {
  return files.map((f) => ({
    ...f,
    dimensionsStr: f.dimensions?.length > 0 ? f.dimensions.join(', ') : '',
  }));
}

function sortDimensionsByViolationSeverity(dimensions) {
  return [...dimensions]
    .filter((d) => (d.violations || []).length > 0)
    .map((d) => {
      const counts = { critical: 0, major: 0, minor: 0 };
      (d.violations || []).forEach((v) => {
        const s = (v.severity || 'minor').toLowerCase();
        if (counts[s] !== undefined) counts[s]++;
      });
      return { ...d, _c: counts };
    })
    .sort((a, b) => {
      if (b._c.critical !== a._c.critical) return b._c.critical - a._c.critical;
      if (b._c.major !== a._c.major) return b._c.major - a._c.major;
      return b._c.minor - a._c.minor;
    });
}

// ---------------------------------------------------------------------------
// Run-specific overview panel
// ---------------------------------------------------------------------------

export default function RunOverviewPanel({ dashboard, selectedRunId, onDimensionClick, onFileClick }) {
  const runSummary = useMemo(
    () => buildRunSummary(dashboard?.dimensions),
    [dashboard]
  );

  const runTopFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(dashboard?.dimensions || [])),
    [dashboard]
  );

  const dimensionsWithViolations = useMemo(
    () => sortDimensionsByViolationSeverity(dashboard?.dimensions || []),
    [dashboard]
  );

  const runScoreDelta = useMemo(() => {
    const trendSeries = dashboard?.trend || [];
    const selectedRunId = dashboard?.selectedRun?.runId;
    const idx = trendSeries.findIndex((t) => t.runId === selectedRunId);
    if (idx < 0 || idx + 1 >= trendSeries.length) return null;
    const curr = parseFloat(trendSeries[idx].numericAverage);
    const prev = parseFloat(trendSeries[idx + 1].numericAverage);
    if (isNaN(curr) || isNaN(prev)) return null;
    return (curr - prev).toFixed(1);
  }, [dashboard]);

  const runUniquePrinciples = useMemo(() => {
    const violations = (dashboard?.dimensions || []).flatMap((d) => d.violations || []);
    return new Set(violations.map((v) => v.principle).filter(Boolean)).size;
  }, [dashboard]);

  if (!dashboard) {
    return <p className="empty-state">Loading run data...</p>;
  }

  return (
    <>
      <section className="acc-eval-panel panel">
        <div className="acc-eval-top">
          <span className="acc-eval-date">{dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId)}</span>
          {(dashboard?.dimensions || []).some((d) => (d.violations?.length || 0) > 0) && (
            <CopyButton
              label="Fix plan"
              onClick={() => {
                const allViolations = (dashboard.dimensions || []).flatMap(
                  (d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
                );
                navigator.clipboard.writeText(
                  buildDimensionPlanFromViolations(dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId), allViolations)
                );
              }}
            />
          )}
        </div>

        <div className="acc-eval-hero">
          <span className={`acc-eval-grade-chip chip ${scoreColorClass(runSummary.numericAverage)}`}>
            {runSummary.overallGrade || '—'}
          </span>
          <div className="acc-eval-score-row">
            <span className="acc-eval-score">{runSummary.numericAverage || '—'}</span>
            <span className="acc-eval-score-denom">/10</span>
          </div>
          {runScoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={runScoreDelta} showLabel={false} />
            </div>
          )}
        </div>

        <div className="acc-eval-stats-grid">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{runSummary.totalViolations || 0}</span>
            <div className="acc-eval-tags">
              {(runSummary.severity?.critical || 0) > 0 && (
                <span className="severity-tag critical">{runSummary.severity.critical} critical</span>
              )}
              {(runSummary.severity?.major || 0) > 0 && (
                <span className="severity-tag major">{runSummary.severity.major} major</span>
              )}
              {(runSummary.severity?.minor || 0) > 0 && (
                <span className="severity-tag minor">{runSummary.severity.minor} minor</span>
              )}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance</span>
            <span className="acc-eval-stat-value">{runSummary.totalCompliance || 0}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Ratio</span>
            <span className="acc-eval-stat-value">
              {(() => {
                const v = runSummary.totalViolations || 0;
                const c = runSummary.totalCompliance || 0;
                if (v === 0) return '—';
                return `1:${Math.round(c / v)}`;
              })()}
            </span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files Affected</span>
            <span className="acc-eval-stat-value">{runTopFiles.length}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{runUniquePrinciples}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Dimensions</span>
            <span className="acc-eval-stat-value">{runSummary.dimensionCount || 0}</span>
          </div>
        </div>
      </section>

      <div className="dimensions-header">
        <h3 className="dimensions-title">Dimensions Analyzed</h3>
      </div>
      <div className="dimensions-panel">
        <div className="dimensions-grid">
          {[...(dashboard?.dimensions || [])]
            .sort((a, b) => a.dimension.localeCompare(b.dimension))
            .map((item) => {
              const currScore = parseFloat(item.overallScore);
              const prevScore = parseFloat(item.previousScore);
              const delta =
                !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
              return (
                <article
                  key={item.dimension}
                  className="qd-card"
                  onClick={() => onDimensionClick(item, selectedRunId)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onDimensionClick(item, selectedRunId); } }}
                >
                  <div className="qd-card-header">
                    <span className="qd-card-name">{item.dimension}</span>
                    <span className={`chip small ${gradeColorClass(item.overallGrade)}`}>
                      {item.overallGrade || '—'}
                    </span>
                  </div>
                  <div className="qd-card-score-row">
                    <span className="qd-card-score-main">
                      <span className="qd-card-score">{splitScore(item.overallScore).value}</span>
                      {splitScore(item.overallScore).denom && (
                        <span className="qd-card-score-denom">
                          {splitScore(item.overallScore).denom}
                        </span>
                      )}
                    </span>
                    <TrendBadge delta={delta} />
                  </div>
                  <div className="qd-card-stats">
                    {(item.totals?.violationCount ?? 0) > 0 && (
                      <span className="qd-card-stat-violations">
                        {item.totals.violationCount} violations
                      </span>
                    )}
                    {(item.totals?.complianceCount ?? 0) > 0 && (
                      <span className="qd-card-stat-compliance">
                        {item.totals.complianceCount} compliant
                      </span>
                    )}
                  </div>
                  <div className="qd-card-footer">
                    <span className="qd-card-date">{item.fromDateLabel || dashboard?.selectedRun?.dateLabel || formatRunId(item.fromRunId || selectedRunId)}</span>
                  </div>
                </article>
              );
            })}
        </div>
      </div>

      {dimensionsWithViolations.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Dimension</h3>
            <span className="section-count">
              {dimensionsWithViolations.length} dimensions analyzed
            </span>
          </div>
          <section className="panel violations-panel expandable">
            <div className="dimension-violations-list">
              {dimensionsWithViolations.map((dim) => (
                <DimensionViolationsRow
                  key={dim.dimension}
                  dimension={dim}
                  onClick={() => onDimensionClick(dim, selectedRunId)}
                />
              ))}
            </div>
          </section>
        </>
      )}

      {runTopFiles.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by File</h3>
            <span className="section-count">{runTopFiles.length} files</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <TopOffendingFilesTable files={runTopFiles} onFileClick={onFileClick} />
            </div>
          </section>
        </>
      )}
    </>
  );
}
