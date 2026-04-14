import RunNavigator from '../features/dashboard/components/RunNavigator.jsx';
import { formatRunId, extDisplayName } from '../utils/formatters.js';

const MAX_DISPLAYED_STATS = 5;

function LanguageStats({ stats, totalFiles }) {
  const sorted = stats ? Object.entries(stats).sort(([, a], [, b]) => b - a).slice(0, MAX_DISPLAYED_STATS) : [];
  if (!totalFiles && sorted.length === 0) return null;
  const total = totalFiles || (sorted.length > 0 ? sorted.reduce((sum, [, c]) => sum + c, 0) : null);
  return (
    <div className="content-header-stats">
      {total && (
        <span className="content-stat">
          <span className="content-stat-num">{total.toLocaleString()}</span>
          <span className="content-stat-label">files</span>
        </span>
      )}
      {sorted.map(([lang, count]) => (
        <span key={lang} className="content-stat">
          <span className="content-stat-num">{count}</span>
          <span className="content-stat-label">{extDisplayName(lang)}</span>
        </span>
      ))}
    </div>
  );
}

function CoverageStat({ totalFiles, analyzedFiles }) {
  if (!totalFiles || totalFiles === 0) return null;
  const pct = analyzedFiles != null ? Math.round((analyzedFiles / totalFiles) * 100) : null;
  if (pct == null) return null;
  return (
    <>
      <span className="content-header-sep" aria-hidden="true">·</span>
      <span className="content-stat">
        <span className="content-stat-num" style={{ color: 'var(--color-accent)' }}>{pct}%</span>
        <span className="content-stat-label">analyzed</span>
      </span>
    </>
  );
}

export default function ProjectHeader({
  project = {},
  navigation = {},
}) {
  const { displayName, parent, parentId, meta } = project;
  const { onProjectChange, showRunNav, runNavProps } = navigation;
  return (
    <header className="content-header">
      <div className="content-header-top">
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
        {showRunNav && runNavProps && (
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
        )}
      </div>
      {meta && (
        <div className="content-header-meta">
          <LanguageStats stats={meta.languageStats} totalFiles={meta.totalFiles} />
          <CoverageStat totalFiles={meta.totalFiles} analyzedFiles={meta.analyzedFiles} />
          {meta.repository && (
            <span className="content-meta-text">{meta.repository}</span>
          )}
        </div>
      )}
    </header>
  );
}
