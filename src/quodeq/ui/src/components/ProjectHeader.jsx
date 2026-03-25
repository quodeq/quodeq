import RunNavigator from '../features/dashboard/components/RunNavigator.jsx';
import { formatRunId } from '../utils/formatters.js';

export default function ProjectHeader({
  project = {},
  navigation = {},
}) {
  const { displayName, parent, parentId, meta } = project;
  const { onProjectChange, showRunNav, runNavProps } = navigation;
  return (
    <header className="content-header">
      <div className="content-header-left">
        <h1 className="content-project-name">
          {parent && (
            <>
              <span
                className="content-project-parent content-project-parent--link"
                role="button"
                tabIndex={0}
                onClick={() => parentId && onProjectChange(parentId)}
                onKeyDown={(e) => { if (e.key === 'Enter' && parentId) onProjectChange(parentId); }}
              >{parent}</span>
              <span className="content-project-sep">&rsaquo;</span>
            </>
          )}
          {displayName}
        </h1>
        {meta && (
          <div className="content-meta-row">
            {meta.repository && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Repository</span>
                <span className="content-meta-chip-value">{meta.repository}</span>
              </span>
            )}
            {meta.discipline && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Discipline</span>
                <span className="content-meta-chip-value">{meta.discipline}</span>
              </span>
            )}
            {meta.totalFiles && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Source files</span>
                <span className="content-meta-chip-value">{meta.totalFiles.toLocaleString()}</span>
              </span>
            )}
            {meta.languageStats && Object.keys(meta.languageStats).length > 0 && (
              <span className="content-meta-chip">
                <span className="content-meta-chip-label">Languages</span>
                <span className="content-meta-chip-value">
                  {Object.entries(meta.languageStats)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 5)
                    .map(([lang, count]) => `${lang} (${count})`)
                    .join(', ')}
                </span>
              </span>
            )}
          </div>
        )}
      </div>
      {showRunNav && runNavProps && (
        <div className="history-run-nav">
          <RunNavigator
            currentRun={runNavProps.currentDayLabel || formatRunId(runNavProps.currentOverviewRun, runNavProps.availableRuns[runNavProps.overviewRunIndex]?.dateLabel)}
            isLatest={runNavProps.overviewRunIndex === 0}
            isOldest={runNavProps.overviewRunIndex >= runNavProps.availableRuns.length - 1}
            actions={{
              onPrev: runNavProps.onRunPrev,
              onNext: runNavProps.onRunNext,
              onLatest: runNavProps.onRunLatest,
            }}
          />
        </div>
      )}
    </header>
  );
}
