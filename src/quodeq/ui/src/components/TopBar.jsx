/**
 * TopBar — global app header sitting above the page content.
 *
 * Layout (left → right):
 *   [ breadcrumb `project / activeTab` ]           [ live pill | model pill | ⌘K | Report | + Evaluate ]
 *
 * Stateless; the parent passes the data it has.
 */

function Dot({ ok }) {
  return <span className={`topbar-dot ${ok ? 'topbar-dot--ok' : 'topbar-dot--err'}`} aria-hidden="true" />;
}

const TAB_TITLES = {
  overview: 'Overview',
  violations: 'Violations',
  map: 'Map',
  history: 'History',
  evaluate: 'Evaluate',
  standards: 'Standards',
  settings: 'Settings',
  projects: 'Projects',
  help: 'Help',
  file: 'File',
  evalprinciple: 'Principle',
  finding: 'Finding',
  explorer: 'Explorer',
};

function BurgerIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

export default function TopBar({
  projectName,
  activeTab,
  serverConnected,
  serverUrl,
  provider,
  model,
  onReport,
  onEvaluate,
  evaluating = false,
  onProviderClick,
  onMenuToggle,
}) {
  const tabTitle = TAB_TITLES[activeTab] || activeTab || '';
  return (
    <header className="topbar">
      {onMenuToggle && (
        <button
          type="button"
          className="topbar-menu-btn"
          onClick={onMenuToggle}
          aria-label="Open menu"
        >
          <BurgerIcon />
        </button>
      )}
      <div className="topbar-breadcrumb">
        {projectName && <span className="topbar-breadcrumb-parent">{projectName}</span>}
        {projectName && tabTitle && <span className="topbar-breadcrumb-sep">/</span>}
        {tabTitle && <span className="topbar-breadcrumb-current">{tabTitle}</span>}
      </div>

      <div className="topbar-actions">
        {(provider || model) && (
          onProviderClick ? (
            <button
              type="button"
              className="topbar-pill topbar-pill--button"
              onClick={onProviderClick}
              title="Open Settings to change provider or model"
            >
              {provider && <span>{provider}</span>}
              {provider && model && <span className="topbar-pill-sep">·</span>}
              {model && <span className="topbar-pill-muted">{model}</span>}
            </button>
          ) : (
            <span className="topbar-pill">
              {provider && <span>{provider}</span>}
              {provider && model && <span className="topbar-pill-sep">·</span>}
              {model && <span className="topbar-pill-muted">{model}</span>}
            </span>
          )
        )}

        {onReport && (
          <button type="button" className="topbar-btn" onClick={onReport}>
            Report
          </button>
        )}
        {onEvaluate && (
          <button
            type="button"
            className={`topbar-btn topbar-btn--evaluate${evaluating ? ' topbar-btn--evaluate--running' : ''}`}
            onClick={onEvaluate}
            aria-live="polite"
          >
            {evaluating ? (
              <>
                <span className="topbar-btn__spinner" aria-hidden="true" />
                <span>Evaluating…</span>
              </>
            ) : (
              <>
                <span className="topbar-btn__plus" aria-hidden="true">+</span>
                <span>Evaluate</span>
              </>
            )}
          </button>
        )}
      </div>
    </header>
  );
}
