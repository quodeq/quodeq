import RunNavigator from '../features/dashboard/components/RunNavigator.jsx';
import { formatRunId } from '../utils/formatters.js';

export default function ProjectHeader({
  selectedDisplayName,
  selectedProjectParent,
  selectedProjectParentId,
  onProjectChange,
  headerMeta,
  showRunNav,
  currentOverviewRun,
  overviewRunIndex,
  availableRuns,
  onRunPrev,
  onRunNext,
  onRunLatest,
  onViewRun,
}) {
  return (
    <header className="content-header">
      <div className="content-header-left">
        <h1 className="content-project-name">
          {selectedProjectParent && (
            <>
              <span
                className="content-project-parent content-project-parent--link"
                role="button"
                tabIndex={0}
                onClick={() => selectedProjectParentId && onProjectChange(selectedProjectParentId)}
                onKeyDown={(e) => { if (e.key === 'Enter' && selectedProjectParentId) onProjectChange(selectedProjectParentId); }}
              >{selectedProjectParent}</span>
              <span className="content-project-sep">&rsaquo;</span>
            </>
          )}
          {selectedDisplayName}
        </h1>
        {headerMeta && (
          <div className="content-meta-row">
            {headerMeta.repository && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Repository</span>
                <span className="content-meta-chip-value">{headerMeta.repository}</span>
              </span>
            )}
            {headerMeta.discipline && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Discipline</span>
                <span className="content-meta-chip-value">{headerMeta.discipline}</span>
              </span>
            )}
            {headerMeta.totalFiles && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Source files</span>
                <span className="content-meta-chip-value">{headerMeta.totalFiles.toLocaleString()}</span>
              </span>
            )}
          </div>
        )}
      </div>
      {showRunNav && (
        <RunNavigator
          currentRun={formatRunId(currentOverviewRun, availableRuns[overviewRunIndex]?.dateLabel)}
          isLatest={overviewRunIndex === 0}
          isOldest={overviewRunIndex >= availableRuns.length - 1}
          onPrev={onRunPrev}
          onNext={onRunNext}
          onLatest={onRunLatest}
          onView={onViewRun}
        />
      )}
    </header>
  );
}
