import { useMemo, useState } from 'react';
import { useDashboard } from '../hooks/useDashboard.js';
import DimensionCard from './DimensionCard.jsx';
import DimensionViolationsRow from './DimensionViolationsRow.jsx';
import ProjectSelector from './ProjectSelector.jsx';
import RunNavigator from './RunNavigator.jsx';
import TopOffendingFilesTable from './TopOffendingFilesTable.jsx';
import ViolationsByPrincipleTable from './ViolationsByPrincipleTable.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { buildTopOffendingFiles } from '../../../utils/explorerUtils.js';
import { formatRunId, gradeColorClass, mostFrequentGrade, splitScore } from '../../../utils/formatters.js';

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
// Accumulated overview panel
// ---------------------------------------------------------------------------

function AccumulatedOverviewPanel({
  accumulated,
  accumulatedDimensions,
  availableRuns,
  overviewRunIndex,
  onDimensionClick,
  onFileClick,
  onPrincipleClick,
}) {
  const currentOverviewRun = availableRuns[overviewRunIndex]?.runId || 'latest';
  const referenceRun = overviewRunIndex === 0 ? availableRuns[0]?.runId : currentOverviewRun;

  // Derived accumulated stats
  const accumulatedTopFiles = useMemo(
    () => withDimensionsStr(buildTopOffendingFiles(accumulatedDimensions)),
    [accumulatedDimensions]
  );

  const accumulatedViolationsByPrinciple = useMemo(
    () =>
      accumulatedDimensions.flatMap((d) =>
        (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
      ),
    [accumulatedDimensions]
  );

  const accumulatedScoreDelta = useMemo(() => {
    const prevScores = accumulatedDimensions
      .map((d) => parseFloat(d.previousScore))
      .filter((v) => !isNaN(v));
    if (prevScores.length === 0) return null;
    const prevAvg = prevScores.reduce((a, b) => a + b, 0) / prevScores.length;
    const currAvg = parseFloat(accumulated?.summary?.numericAverage);
    if (isNaN(currAvg)) return null;
    return (currAvg - prevAvg).toFixed(1);
  }, [accumulatedDimensions, accumulated]);

  const accumulatedLastDate = useMemo(() => {
    const ids = accumulatedDimensions.map((d) => d.fromRunId).filter(Boolean);
    if (ids.length === 0) return null;
    return formatRunId(ids.sort().reverse()[0]);
  }, [accumulatedDimensions]);

  const accumulatedUniquePrinciples = useMemo(
    () => new Set(accumulatedViolationsByPrinciple.map((v) => v.principle).filter(Boolean)).size,
    [accumulatedViolationsByPrinciple]
  );

  const dimensionsWithViolations = useMemo(
    () => sortDimensionsByViolationSeverity(accumulatedDimensions),
    [accumulatedDimensions]
  );

  return (
    <>
      {/* Accumulated summary hero */}
      <section className="acc-eval-panel panel">
        <div className="acc-eval-top">
          <span className="acc-eval-label">Accumulated Evaluation</span>
          {accumulatedLastDate && (
            <span className="acc-eval-date">Last evaluated {accumulatedLastDate}</span>
          )}
        </div>

        <div className="acc-eval-hero">
          <span
            className={`acc-eval-grade-chip chip ${gradeColorClass(accumulated?.summary?.overallGrade)}`}
          >
            {accumulated?.summary?.overallGrade || '—'}
          </span>
          <div className="acc-eval-score-row">
            <span className="acc-eval-score">{accumulated?.summary?.numericAverage || '—'}</span>
            <span className="acc-eval-score-denom">/10</span>
          </div>
          {accumulatedScoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={accumulatedScoreDelta} showLabel={true} />
            </div>
          )}
        </div>

        <div className="acc-eval-stats-grid">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">
              {accumulated?.summary?.totalViolations || 0}
            </span>
            <div className="acc-eval-tags">
              {(accumulated?.summary?.severity?.critical || 0) > 0 && (
                <span className="severity-tag critical">
                  {accumulated.summary.severity.critical} critical
                </span>
              )}
              {(accumulated?.summary?.severity?.major || 0) > 0 && (
                <span className="severity-tag major">
                  {accumulated.summary.severity.major} major
                </span>
              )}
              {(accumulated?.summary?.severity?.minor || 0) > 0 && (
                <span className="severity-tag minor">
                  {accumulated.summary.severity.minor} minor
                </span>
              )}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Files Affected</span>
            <span className="acc-eval-stat-value">{accumulatedTopFiles.length}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Principles</span>
            <span className="acc-eval-stat-value">{accumulatedUniquePrinciples}</span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliant</span>
            <span className="acc-eval-stat-value">
              {accumulated?.summary?.totalCompliance || 0}
            </span>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Dimensions</span>
            <span className="acc-eval-stat-value">
              {accumulated?.summary?.dimensionCount || 0}
            </span>
          </div>
        </div>
      </section>

      {/* Quality dimension cards */}
      <div className="dimensions-header">
        <h3 className="dimensions-title">Quality Dimensions</h3>
      </div>
      <div className="dimensions-panel">
        <div className="dimensions-grid">
          {[...accumulatedDimensions]
            .sort((a, b) => a.dimension.localeCompare(b.dimension))
            .map((item) => {
              const isStale = item.fromRunId !== referenceRun;
              const currScore = parseFloat(item.overallScore);
              const prevScore = parseFloat(item.previousScore);
              const delta =
                !isNaN(currScore) && !isNaN(prevScore) ? currScore - prevScore : null;
              return (
                <article
                  key={item.dimension}
                  className={`qd-card${isStale ? ' qd-card-stale' : ''}`}
                  onClick={() => onDimensionClick(item)}
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
                    <TrendBadge delta={delta} trend={item.trend} />
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
                    <span className="qd-card-date">{formatRunId(item.fromRunId)}</span>
                    {isStale && <span className="qd-card-stale-label">Older run</span>}
                  </div>
                </article>
              );
            })}
        </div>
      </div>

      {/* Violations by dimension */}
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
                  onClick={() => onDimensionClick(dim)}
                />
              ))}
            </div>
          </section>
        </>
      )}

      {/* Violations by file */}
      {accumulatedTopFiles.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by File</h3>
            <span className="section-count">{accumulatedTopFiles.length} files</span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <TopOffendingFilesTable
                files={accumulatedTopFiles}
                onFileClick={onFileClick}
              />
            </div>
          </section>
        </>
      )}

      {/* Violations by principle */}
      {accumulatedViolationsByPrinciple.length > 0 && (
        <>
          <div className="section-header">
            <h3 className="section-title">Violations by Principle</h3>
            <span className="section-count">
              {
                new Set(
                  accumulatedViolationsByPrinciple.map((v) => v.principle).filter(Boolean)
                ).size
              }{' '}
              principles
            </span>
          </div>
          <section className="panel wide-panel offending-panel">
            <div className="trend-table-wrap">
              <ViolationsByPrincipleTable
                violations={accumulatedViolationsByPrinciple}
                onPrincipleClick={onPrincipleClick}
              />
            </div>
          </section>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Run-specific overview panel
// ---------------------------------------------------------------------------

function RunOverviewPanel({ dashboard, selectedRunId, onDimensionClick, onFileClick }) {
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

  if (!dashboard) {
    return <p className="empty-state">Loading run data...</p>;
  }

  return (
    <>
      <section className="overview-summary">
        <h3 className="run-evaluation-title">{formatRunId(selectedRunId)}</h3>
        <div className="overview-summary-row">
          <article className="overview-stat-card overview-stat-grade">
            <p className="overview-stat-label">Grade</p>
            <p className="overview-stat-value big">{runSummary.overallGrade}</p>
            {runSummary.numericAverage && (
              <p className="overview-stat-sub">{runSummary.numericAverage}/10</p>
            )}
          </article>
          <article className="overview-stat-card">
            <p className="overview-stat-label">Violations</p>
            <p className="overview-stat-value">{runSummary.totalViolations}</p>
            <div className="overview-severity-row">
              <span className="severity-badge severity-critical">
                {runSummary.severity.critical} critical
              </span>
              <span className="severity-badge severity-major">
                {runSummary.severity.major} major
              </span>
              <span className="severity-badge severity-minor">
                {runSummary.severity.minor} minor
              </span>
            </div>
          </article>
          <article className="overview-stat-card">
            <p className="overview-stat-label">Compliance</p>
            <p className="overview-stat-value">{runSummary.totalCompliance}</p>
          </article>
          <article className="overview-stat-card">
            <p className="overview-stat-label">Dimensions</p>
            <p className="overview-stat-value">{runSummary.dimensionCount}</p>
          </article>
        </div>
      </section>

      {/* Dimension cards */}
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
                    <TrendBadge delta={delta} trend={item.trend} />
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
                    <span className="qd-card-date">{formatRunId(item.fromRunId || selectedRunId)}</span>
                  </div>
                </article>
              );
            })}
        </div>
      </div>

      {/* Violations by dimension */}
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

      {/* Violations by file */}
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

// ---------------------------------------------------------------------------
// DashboardPage
// ---------------------------------------------------------------------------

/**
 * Main dashboard view orchestrator.
 *
 * Props:
 *   selectedProject  - current project name (string)
 *   selectedRun      - current run ID or 'latest' (string)
 *   projects         - array of project objects ({ name }) for the project selector
 *   onProjectChange  - called with new project name when user switches projects
 *   onRunChange      - called with new run ID when user switches runs
 *   onNavigate       - called with (page, params) to push to the navigation stack
 */
export default function DashboardPage({
  selectedProject,
  selectedRun,
  projects = [],
  onProjectChange,
  onRunChange,
  onNavigate,
}) {
  const { dashboard, accumulated, loading, error, availableRuns } = useDashboard({
    selectedProject,
    selectedRun,
  });

  // Dashboard-local UI state
  const [themePreference, setThemePreference] = useState(
    () => localStorage.getItem('cc-theme') ?? 'system'
  );
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [focusedDimension, setFocusedDimension] = useState(null);
  const [overviewRunIndex, setOverviewRunIndex] = useState(0);

  const applyTheme = (pref) => {
    setThemePreference(pref);
    localStorage.setItem('cc-theme', pref);
    if (pref === 'system') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', pref);
    }
  };

  // The current run displayed in the RunNavigator (index 0 = latest).
  const currentOverviewRun = availableRuns[overviewRunIndex]?.runId || 'latest';
  const selectedRunId = dashboard?.selectedRun?.runId || selectedRun;

  // Accumulated dimensions (all dimensions, latest of each).
  const accumulatedDimensions = accumulated?.dimensions || [];

  // Focused single-dimension view data.
  const focusedDimensionData = useMemo(() => {
    if (!focusedDimension) return null;
    return (dashboard?.dimensions || []).find((d) => d.dimension === focusedDimension) || null;
  }, [focusedDimension, dashboard]);

  // Handlers for navigating to explorer/file/principle detail pages.
  const handleDimensionCardClick = (item, runId) => {
    if (onNavigate) {
      onNavigate('explorer', { dimension: item.dimension, runId: runId || item.fromRunId });
    }
  };

  const handleAccumulatedDimensionClick = (item) => {
    if (onNavigate) {
      onNavigate('explorer', { dimension: item.dimension, runId: item.fromRunId });
    }
  };

  const handleFileClick = (fileObj) => {
    if (onNavigate) {
      onNavigate('file', { file: fileObj });
    }
  };

  const handlePrincipleClick = (principleObj) => {
    if (onNavigate) {
      onNavigate('principle', { principle: principleObj });
    }
  };

  // RunNavigator handlers — navigate through the available runs list.
  const handleRunPrev = () => {
    const newIndex = Math.min(overviewRunIndex + 1, availableRuns.length - 1);
    setOverviewRunIndex(newIndex);
    if (onRunChange) onRunChange(availableRuns[newIndex]?.runId || 'latest');
  };

  const handleRunNext = () => {
    const newIndex = Math.max(overviewRunIndex - 1, 0);
    setOverviewRunIndex(newIndex);
    if (onRunChange) onRunChange(availableRuns[newIndex]?.runId || 'latest');
  };

  const handleRunLatest = () => {
    setOverviewRunIndex(0);
    if (onRunChange) onRunChange(availableRuns[0]?.runId || 'latest');
  };

  const handleRunView = () => {
    if (onNavigate) {
      onNavigate('run', { runId: currentOverviewRun });
    }
  };

  // Empty state when there are no projects.
  if (!projects || projects.length === 0) {
    return (
      <section className="empty-state">
        <h2>No analyzed projects yet</h2>
        <p>Run an evaluation to get started.</p>
      </section>
    );
  }

  return (
    <div className="dashboard-page">
      {/* Project and run selectors */}
      <ProjectSelector
        projects={projects}
        selectedProject={selectedProject}
        selectedRun={selectedRunId}
        runs={availableRuns}
        onProjectChange={(project) => {
          setOverviewRunIndex(0);
          if (onProjectChange) onProjectChange(project);
        }}
        onRunChange={(run) => {
          setOverviewRunIndex(
            availableRuns.findIndex((r) => r.runId === run) || 0
          );
          if (onRunChange) onRunChange(run);
        }}
      />

      {/* Run navigation */}
      {availableRuns.length > 0 && (
        <RunNavigator
          currentRun={formatRunId(currentOverviewRun)}
          isLatest={overviewRunIndex === 0}
          isOldest={overviewRunIndex >= availableRuns.length - 1}
          onPrev={handleRunPrev}
          onNext={handleRunNext}
          onLatest={handleRunLatest}
          onView={handleRunView}
        />
      )}

      {/* Error */}
      {error && <p className="inline-error">{error}</p>}

      {/* Loading */}
      {loading && <p className="loading">Loading dashboard...</p>}

      {/* Main content */}
      {!loading && dashboard && accumulated && (
        <>
          {/* Focused single dimension */}
          {focusedDimension ? (
            <div className="dimensions-panel">
              <div className="dimensions-header">
                <h3 className="dimensions-title">{focusedDimension}</h3>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setFocusedDimension(null)}
                >
                  Show all
                </button>
              </div>
              <DimensionCard
                title={focusedDimension}
                dimension={focusedDimensionData}
                isSingleFocus={true}
              />
            </div>
          ) : (
            <AccumulatedOverviewPanel
              accumulated={accumulated}
              accumulatedDimensions={accumulatedDimensions}
              availableRuns={availableRuns}
              overviewRunIndex={overviewRunIndex}
              onDimensionClick={handleAccumulatedDimensionClick}
              onFileClick={handleFileClick}
              onPrincipleClick={handlePrincipleClick}
            />
          )}
        </>
      )}

      {!loading && dashboard && !accumulated && (
        <p className="empty-state">Loading accumulated data...</p>
      )}

      {/* Settings toggle button */}
      <button
        type="button"
        className="settings-panel-toggle"
        onClick={() => setShowSettingsPanel((v) => !v)}
        title="Settings"
        aria-label="Toggle settings panel"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>

      {/* Settings panel */}
      {showSettingsPanel && (
        <aside className="settings-panel panel">
          <h4 className="settings-panel-title">Settings</h4>

          <div className="settings-section">
            <p className="settings-label">Theme</p>
            <div className="theme-toggle-group">
              {['light', 'system', 'dark'].map((pref) => (
                <button
                  key={pref}
                  type="button"
                  className={`theme-toggle-btn${themePreference === pref ? ' active' : ''}`}
                  onClick={() => applyTheme(pref)}
                >
                  {pref.charAt(0).toUpperCase() + pref.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div className="settings-section">
            <label className="settings-toggle-row">
              <span className="settings-label">Compare mode</span>
              <input
                type="checkbox"
                checked={compareMode}
                onChange={(e) => setCompareMode(e.target.checked)}
              />
            </label>
          </div>
        </aside>
      )}
    </div>
  );
}
