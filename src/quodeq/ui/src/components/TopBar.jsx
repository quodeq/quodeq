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
import { useSidePane } from '../features/side-pane/index.js';
import { FileTextIcon, SparkleIcon } from './CopyButton.jsx';
import ServerStatusDot from './ServerStatusDot.jsx';
import { AssistantLauncherButton } from './AssistantLauncherButton.jsx';
import { TerminalLauncherButton } from './TerminalLauncherButton.jsx';

function SidePaneSpecButton({ type, label, icon, modifier }) {
  const ctx = useSidePane();
  const spec = ctx.getRegisteredSpec ? ctx.getRegisteredSpec(type) : null;
  if (!spec) return null;
  const inDock = ctx.hasWindow(spec.id);
  // Don't disable when at cap — let the click flow through addWindow so the
  // provider's at-cap toast fires. A silently-disabled button gives no
  // feedback about why nothing happens.
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--${modifier}${inDock ? ` topbar-btn--${modifier}--open` : ''}`}
      aria-pressed={inDock}
      title={inDock ? `Close ${label.toLowerCase()}` : `Open ${label.toLowerCase()}`}
      onClick={() => {
        if (inDock) ctx.removeWindow(spec.id);
        else ctx.addWindow(spec);
      }}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function ReportToolbarButton() {
  return <SidePaneSpecButton type="report" label="Report" icon={<FileTextIcon />} modifier="report" />;
}

function FixPlanToolbarButton() {
  return <SidePaneSpecButton type="fixplan" label="Fix plan" icon={<SparkleIcon />} modifier="fixplan" />;
}

function BurgerIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="9" y1="4" x2="9" y2="20" />
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
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
  onSelectProject,
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
  /* 'local' | 'shared' — shared projects are read-only in this app (no
     mutation routes exist on the backend), so the assistant (which can take
     write actions like dismiss/verify) is not offered for them. */
  selectedSource = 'local',
}) {
  return (
    <header className="topbar pywebview-drag-region">
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

      {/* Desktop: full breadcrumb chain. Mobile: tappable project + current
          page title. The breadcrumb slot is display:none on mobile and this
          row is display:none on desktop, so only one project control is ever
          live per viewport. */}
      {breadcrumb && <div className="topbar-breadcrumb-slot">{breadcrumb}</div>}
      <div className="topbar-mobile-title" aria-hidden={!mobileTitle && !projectName}>
        {projectName && onSelectProject && (
          <button
            type="button"
            className="topbar-mobile-project"
            onClick={onSelectProject}
            title="Open projects"
          >
            {projectName}
          </button>
        )}
        {projectName && onSelectProject && mobileTitle && (
          <span className="topbar-mobile-sep" aria-hidden="true">/</span>
        )}
        {mobileTitle && <span className="topbar-mobile-page">{mobileTitle}</span>}
      </div>

      <div className="topbar-spacer" />

      <div className="topbar-actions">
        <ServerStatusDot connected={serverConnected} url={serverUrl} />
        <FixPlanToolbarButton />
        <ReportToolbarButton />

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

        {selectedSource !== 'shared' && <AssistantLauncherButton />}
        <TerminalLauncherButton />

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
