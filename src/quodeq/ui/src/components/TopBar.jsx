/**
 * TopBar — global app header sitting above the page content.
 *
 * Desktop layout (left → right):
 *   [ address (projectName / … / page) ]
 *   [ status | fix plan · report | theme · assistant · terminal | model | ▸ evaluate ]
 * Action buttons show their icon at rest and expand their label on hover;
 * the cluster is right-anchored so expansion pushes leftward and the primary
 * never moves. While a run is live a progress chip replaces the (dimmed)
 * Evaluate button and a hairline progress line runs along the bottom edge.
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
import { TopBarProviderPill } from './TopBarProviderPill.jsx';
import { TopBarRunChip, TopBarProgressHairline } from './TopBarRunChip.jsx';
import { t } from '../strings/index.js';

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
      <span className="topbar-btn__label">{label}</span>
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

function MobileTitleRow({ projectName, onSelectProject, mobileTitle }) {
  return (
    <div className="topbar-mobile-title" aria-hidden={!mobileTitle && !projectName}>
      {projectName && onSelectProject && (
        <button
          type="button"
          className="topbar-mobile-project"
          onClick={onSelectProject}
          title={t('common.openProjects')}
        >
          {projectName}
        </button>
      )}
      {projectName && onSelectProject && mobileTitle && (
        <span className="topbar-mobile-sep" aria-hidden="true">/</span>
      )}
      {mobileTitle && <span className="topbar-mobile-page">{mobileTitle}</span>}
    </div>
  );
}

function ThemeToggleButton({ onToggleTheme, effectiveDark }) {
  if (!onToggleTheme) return null;
  return (
    <button
      type="button"
      className="topbar-btn topbar-btn--icon topbar-btn--theme"
      onClick={onToggleTheme}
      aria-label={effectiveDark ? t('common.switchToLight') : t('common.switchToDark')}
      title={effectiveDark ? t('common.switchToLight') : t('common.switchToDark')}
    >
      {effectiveDark ? <SunIcon /> : <MoonIcon />}
      <span className="topbar-btn__label">{effectiveDark ? 'light' : 'dark'}</span>
    </button>
  );
}

function EvaluateButton({ onEvaluate, evaluating }) {
  if (!onEvaluate) return null;
  return (
    <button
      type="button"
      className={`topbar-btn topbar-btn--evaluate${evaluating ? ' topbar-btn--evaluate--running' : ''}`}
      onClick={evaluating ? undefined : onEvaluate}
      aria-disabled={evaluating || undefined}
      title={evaluating ? t('evaluate.alreadyRunningShort') : undefined}
      aria-live="polite"
    >
      <span className="topbar-btn__play" aria-hidden="true">▸</span>
      <span>{t('common.evaluate')}</span>
    </button>
  );
}

function TopBarActions({
  serverConnected, serverUrl, onToggleTheme, effectiveDark, provider, model, onProviderClick,
  onEvaluate, evaluating, runProgress, onMenuToggle,
}) {
  return (
    <div className="topbar-actions">
      <ServerStatusDot connected={serverConnected} url={serverUrl} />
      <span className="topbar-divider" aria-hidden="true" />

      <FixPlanToolbarButton />
      <ReportToolbarButton />
      <span className="topbar-divider" aria-hidden="true" />

      <ThemeToggleButton onToggleTheme={onToggleTheme} effectiveDark={effectiveDark} />

      <AssistantLauncherButton />
      <TerminalLauncherButton />
      <span className="topbar-divider" aria-hidden="true" />

      <TopBarProviderPill provider={provider} model={model} onProviderClick={onProviderClick} />

      <TopBarRunChip onEvaluate={onEvaluate} evaluating={evaluating} runProgress={runProgress} />
      <EvaluateButton onEvaluate={onEvaluate} evaluating={evaluating} />

      {/* Burger is mobile-only and lives on the right. Desktop hides it. */}
      {onMenuToggle && (
        <button
          type="button"
          className="topbar-menu-btn"
          onClick={onMenuToggle}
          aria-label={t('common.openMenu')}
        >
          <BurgerIcon />
        </button>
      )}
    </div>
  );
}

// Compact-mode back button. Hidden entirely at the root of the nav stack —
// showing a disabled arrow adds visual noise without giving the user
// anything to click.
function CompactBackButton({ canGoBack, onBack }) {
  if (!canGoBack) return null;
  return (
    <button
      type="button"
      className="topbar-back-btn"
      onClick={onBack}
      aria-label={t('common.goBack')}
    >
      <BackIcon />
    </button>
  );
}

/**
 * @param {object} props
 * @param {{dimension: string, percent: number}} [props.runProgress] - While a
 *   run is live, feeds the run chip and the progress hairline along the bar's
 *   bottom edge. Either field may be null before the first progress poll lands.
 * @param {boolean} [props.effectiveDark] - Theme toggle — parent owns the
 *   cycle (light <-> dark within the current family). Reflects what's
 *   actually showing (so "system" on a light OS still renders the moon icon
 *   since the next click will flip to dark).
 * @param {'local'|'shared'} [props.selectedSource] - Shared projects get
 *   read-only assistant sessions server-side, so this no longer gates the
 *   assistant launcher; it still gates the Evaluate button (see App.jsx's
 *   shouldShowEvaluateButton).
 */
export default function TopBar({
  projectName,
  activeTab,
  serverConnected,
  serverUrl,
  provider,
  model,
  onEvaluate,
  evaluating = false,
  runProgress = null,
  onProviderClick,
  onMenuToggle,
  onSelectProject,
  breadcrumb = null,
  mobileTitle = '',
  canGoBack = false,
  onBack,
  effectiveDark = false,
  onToggleTheme,
  selectedSource = 'local',
}) {
  return (
    <header className="topbar pywebview-drag-region">
      <CompactBackButton canGoBack={canGoBack} onBack={onBack} />

      {/* Desktop breadcrumb vs. mobile title row — only one is ever live. */}
      {breadcrumb && <div className="topbar-breadcrumb-slot">{breadcrumb}</div>}
      <MobileTitleRow projectName={projectName} onSelectProject={onSelectProject} mobileTitle={mobileTitle} />

      <div className="topbar-spacer" />

      <TopBarActions
        serverConnected={serverConnected}
        serverUrl={serverUrl}
        onToggleTheme={onToggleTheme}
        effectiveDark={effectiveDark}
        provider={provider}
        model={model}
        onProviderClick={onProviderClick}
        onEvaluate={onEvaluate}
        evaluating={evaluating}
        runProgress={runProgress}
        onMenuToggle={onMenuToggle}
      />

      <TopBarProgressHairline evaluating={evaluating} runProgress={runProgress} />
    </header>
  );
}
