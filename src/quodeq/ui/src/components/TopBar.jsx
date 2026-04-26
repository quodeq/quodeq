/**
 * TopBar — global app header sitting above the page content.
 *
 * Desktop layout (left → right):
 *   [ breadcrumb (projectName / page / …) ]        [ provider pill | Report | + Evaluate ]
 *
 * Mobile layout (left → right):
 *   [ ‹ back ]  [ current page title ]                                          [ burger ]
 *
 * Stateless; the parent passes the data it has.
 */
import { useReportViewer } from '../features/report-viewer/index.js';
import { FileTextIcon } from './CopyButton.jsx';

function Dot({ ok }) {
  return <span className={`topbar-dot ${ok ? 'topbar-dot--ok' : 'topbar-dot--err'}`} aria-hidden="true" />;
}

function BurgerIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
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
  onEvaluate,
  evaluating = false,
  onProviderClick,
  onMenuToggle,
  breadcrumb = null,
  mobileTitle = '',
  canGoBack = false,
  onBack,
  /* Theme toggle — parent owns the cycle (light ↔ dark within the
     current family). `effectiveDark` reflects what's actually showing
     (so "system" on a light OS still renders the moon icon since the
     next click will flip to dark). */
  effectiveDark = false,
  onToggleTheme,
}) {
  const { activeBuilder, isOpen: reportOpen, openReport, closeReport } = useReportViewer();
  return (
    <header className="topbar">
      {/* Compact-mode back button. Hidden entirely at the root of the
          nav stack — showing a disabled arrow adds visual noise without
          giving the user anything to click. */}
      {canGoBack && (
        <button
          type="button"
          className="topbar-back-btn"
          onClick={onBack}
          aria-label="Go back"
        >
          <BackIcon />
        </button>
      )}

      {/* Desktop: full breadcrumb chain. Mobile: just the current page title. */}
      {breadcrumb && <div className="topbar-breadcrumb-slot">{breadcrumb}</div>}
      <div className="topbar-mobile-title" aria-hidden={!mobileTitle}>{mobileTitle}</div>

      <div className="topbar-spacer" />

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

        {onToggleTheme && (
          <button
            type="button"
            className="topbar-btn topbar-btn--icon topbar-btn--theme"
            onClick={onToggleTheme}
            aria-label={effectiveDark ? 'Switch to light theme' : 'Switch to dark theme'}
            title={effectiveDark ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {effectiveDark ? <SunIcon /> : <MoonIcon />}
          </button>
        )}
        {activeBuilder && (
          <button
            type="button"
            className={`topbar-btn topbar-btn--report${reportOpen ? ' topbar-btn--report--open' : ''}`}
            aria-pressed={reportOpen}
            onClick={() => {
              if (reportOpen) {
                closeReport();
              } else {
                openReport({
                  title: activeBuilder.title,
                  markdown: activeBuilder.buildMarkdown(),
                });
              }
            }}
          >
            <FileTextIcon />
            <span>Report</span>
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

        {/* Burger is mobile-only and lives on the right. Desktop hides it. */}
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
      </div>
    </header>
  );
}
