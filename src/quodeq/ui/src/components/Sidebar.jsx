import { ICON_OVERVIEW, ICON_VIOLATIONS, ICON_MAP, ICON_HISTORY, ICON_EVALUATE, ICON_COMPARE, ICON_SETTINGS, ICON_STANDARDS, ICON_HELP, ICON_FOLDER as BASE_ICON_FOLDER } from '../constants/navigation.jsx';
import { cloneElement } from 'react';
import { BRAND_NAME } from '../strings/brand.js';
import { t, LOCALE } from '../strings/index.js';
import { isEvaluatableSource } from '../appGating.js';
import { useSidebarPin } from '../hooks/useSidebarPin.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';
import {
  LOGO_VIEWBOX,
  LOGO_PATH_TRANSFORM,
  LOGO_LEFT_CHEVRON_D,
  LOGO_RIGHT_CHEVRON_D,
  LOGO_Q_D,
  LOGO_NEEDLE_LIGHT_D,
  LOGO_NEEDLE_DARK_D,
  LogoNeedleMask,
} from './brandLogoArt.jsx';
import { NAV_TAB } from '../vocab/navTab.js';

// Unique per component: the onboarding carousel draws the same mark with its
// own mask, and two elements sharing a DOM id would collide when both are
// mounted.
const NEEDLE_MASK_ID = 'needle-hole-mask';

// Folder glyph for the REPOSITORY row — same outline used in the file/folder
// table on FileDetailPage, just sized up for the sidebar rail.
const ICON_FOLDER = cloneElement(BASE_ICON_FOLDER, { width: 18, height: 18 });

function Logo() {
  return (
    <svg viewBox={LOGO_VIEWBOX} role="img" aria-label={BRAND_NAME} width="32" height="32" style={{overflow:'visible'}}>
      <defs>
        <filter id="chevron-glow" x="-25%" y="-25%" width="150%" height="150%">
          <feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="var(--logo-chevron-hover)" floodOpacity="0.28" />
        </filter>
        <LogoNeedleMask id={NEEDLE_MASK_ID} />
      </defs>
      <path id="left-chevron" d={LOGO_LEFT_CHEVRON_D} transform={LOGO_PATH_TRANSFORM} style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
      <path id="right-chevron" d={LOGO_RIGHT_CHEVRON_D} transform={LOGO_PATH_TRANSFORM} style={{fill:'var(--logo-chevron)',cursor:'pointer',transition:'fill 180ms ease, filter 180ms ease'}} />
      <path d={LOGO_Q_D} transform={LOGO_PATH_TRANSFORM} fillRule="evenodd" style={{fill:'var(--logo-q)'}} />
      <g mask={`url(#${NEEDLE_MASK_ID})`}>
        <path d={LOGO_NEEDLE_LIGHT_D} style={{fill:'var(--logo-needle)'}} />
        <path d={LOGO_NEEDLE_DARK_D} style={{fill:'var(--logo-needle-dark)'}} />
      </g>
    </svg>
  );
}

// Cap the count badge text so the absolutely-positioned chip can't grow
// past the rail edge. Thousands collapse to a compact "k" form (1200 -> "1k",
// 12500 -> "13k"), and the title carries the exact number.
const COUNT_K_THRESHOLD = 1000; // four digits is where the chip overflows the rail
function formatNavCount(count) {
  if (count == null) return null;
  if (count >= COUNT_K_THRESHOLD) return `${Math.round(count / COUNT_K_THRESHOLD)}k`;
  return String(count);
}

function NavButton({ id, label, icon, activeTab, onNavTab, count }) {
  const countLabel = formatNavCount(count);
  return (
    <button
      type="button"
      className={`sidebar-nav-item${activeTab === id ? ' active' : ''}`}
      onClick={() => onNavTab(id)}
      title={label}
    >
      {icon}
      <span className="sidebar-nav-label">{label}</span>
      {countLabel != null && (
        <span className="sidebar-nav-count" title={count >= COUNT_K_THRESHOLD ? String(count) : undefined}>
          {countLabel}
        </span>
      )}
    </button>
  );
}

function formatLastEval(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(LOCALE, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch (err) {
    console.warn('[Sidebar] date format failed:', err);
    return null;
  }
}

function SidebarHeader({ isPinned, handleTogglePin, version }) {
  return (
    <div className="sidebar-header">
      <button
        type="button"
        className="sidebar-brand-icon sidebar-brand-icon--toggle"
        onClick={handleTogglePin}
        aria-label={isPinned ? t('common.closeMenu') : t('common.openMenu')}
        aria-expanded={isPinned}
      >
        <Logo />
      </button>
      <span className="sidebar-brand-text">{BRAND_NAME}</span>
      {version && <span className="sidebar-version">{t('common.versionPrefix', { version })}</span>}
    </div>
  );
}

function ProjectTabsNav({ showProjectTabs, showCompareTab, activeTab, handleNav, violationsCount, historyCount }) {
  if (!showProjectTabs && !showCompareTab) return null;
  return (
    <nav className="sidebar-nav sidebar-block">
      {showProjectTabs && (
        <NavButton id={NAV_TAB.OVERVIEW} label="overview" icon={ICON_OVERVIEW} activeTab={activeTab} onNavTab={handleNav} />
      )}
      {showCompareTab && (
        <NavButton id={NAV_TAB.COMPARE} label="compare" icon={ICON_COMPARE} activeTab={activeTab} onNavTab={handleNav} />
      )}
      {showProjectTabs && (
        <>
          <NavButton id={NAV_TAB.VIOLATIONS} label="violations" icon={ICON_VIOLATIONS} activeTab={activeTab} onNavTab={handleNav} count={violationsCount} />
          <NavButton id={NAV_TAB.MAP}        label="map"        icon={ICON_MAP}        activeTab={activeTab} onNavTab={handleNav} />
          <NavButton id={NAV_TAB.HISTORY}    label="history"    icon={ICON_HISTORY}    activeTab={activeTab} onNavTab={handleNav} count={historyCount} />
        </>
      )}
    </nav>
  );
}

function SidebarFooter({ lastEvalStr, activeTab, handleNav, standardsCount }) {
  return (
    <div className="sidebar-footer">
      <div className="sidebar-status">
        {lastEvalStr && (
          <div className="sidebar-status-row">
            <span className="sidebar-status-label">{t('common.lastEval')}</span>
            <span className="sidebar-status-value">{lastEvalStr}</span>
          </div>
        )}
      </div>
      <div className="sidebar-nav sidebar-block sidebar-block--flush">
        <NavButton id={NAV_TAB.SETTINGS} label="settings" icon={ICON_SETTINGS} activeTab={activeTab} onNavTab={handleNav} />
        <NavButton id={NAV_TAB.STANDARDS} label="standards" icon={ICON_STANDARDS} activeTab={activeTab} onNavTab={handleNav} count={standardsCount} />
        <NavButton id={NAV_TAB.HELP} label="help" icon={ICON_HELP} activeTab={activeTab} onNavTab={handleNav} />
      </div>
    </div>
  );
}

function SidebarScrim({ isPinned, onClose }) {
  return (
    <button
      type="button"
      className={`sidebar-scrim${isPinned ? ' sidebar-scrim--visible' : ''}`}
      aria-label={t('common.closeMenu')}
      aria-hidden={!isPinned}
      tabIndex={isPinned ? 0 : -1}
      onClick={onClose}
    />
  );
}

function EvaluateNav({ selectedSource, activeTab, handleNav }) {
  if (!isEvaluatableSource(selectedSource)) return null;
  return (
    <nav className="sidebar-nav sidebar-block">
      <NavButton id={NAV_TAB.EVALUATE} label="evaluate" icon={ICON_EVALUATE} activeTab={activeTab} onNavTab={handleNav} />
    </nav>
  );
}

/** Rail label for the current project: display name, else name, else id. */
function repoNameOf(projectInfo) {
  return projectInfo?.displayName || projectInfo?.name || projectInfo?.id || null;
}

function ProjectsNav({ repoName, activeTab, handleNav }) {
  return (
    <nav className="sidebar-nav sidebar-block">
      <NavButton id={NAV_TAB.PROJECTS} label={repoName || 'project'} icon={ICON_FOLDER} activeTab={activeTab} onNavTab={handleNav} />
    </nav>
  );
}

/**
 * @param {object} props
 * @param {boolean} [props.showProjectTabs] - When false, the project-data tabs
 *   (overview, violations, map, history) are hidden from the sidebar — they
 *   have nothing useful to show until at least one evaluation has completed
 *   for the selected project.
 * @param {boolean} [props.isPinned] - Controlled pin state — when provided,
 *   the parent owns the toggle. Falls back to internal state when the parent
 *   doesn't care.
 * @param {'local'|'shared'} [props.selectedSource] - Evaluation is local-only
 *   (there is no shared mutation route on the backend), so the Evaluate nav
 *   item is hidden outright for a shared selection. Without this, a shared
 *   project's id (which can collide with a local one by design) could start
 *   a real evaluation run whose output writes into the LOCAL project's store.
 * @param {boolean} [props.showCompareTab] - Compare ranks projects against
 *   each other, so it needs at least two analyzed projects to say anything —
 *   below that the tab is hidden as redundant. The parent computes this from
 *   the projects list.
 */
export default function Sidebar({
  activeTab,
  onNavTab,
  showProjectTabs = true,
  projectInfo = null,
  version = null,
  violationsCount = null,
  historyCount = null,
  standardsCount = null,
  lastEvalAt = null,
  isPinned: controlledPinned,
  onPinChange,
  selectedSource = PROJECT_SOURCE.LOCAL,
  showCompareTab = false,
  inert = undefined,
}) {
  const { isPinned, setPinned, handleTogglePin, handleNav } = useSidebarPin({ controlledPinned, onPinChange, onNavTab });
  const repoName = repoNameOf(projectInfo);
  const lastEvalStr = formatLastEval(lastEvalAt);

  return (
    <>
      <SidebarScrim isPinned={isPinned} onClose={() => setPinned(false)} />
      <aside className={`sidebar sidebar--expanded${isPinned ? ' sidebar--pinned' : ''}`} inert={inert}>
        <SidebarHeader isPinned={isPinned} handleTogglePin={handleTogglePin} version={version} />

        <ProjectTabsNav
          showProjectTabs={showProjectTabs}
          showCompareTab={showCompareTab}
          activeTab={activeTab}
          handleNav={handleNav}
          violationsCount={violationsCount}
          historyCount={historyCount}
        />

        <EvaluateNav selectedSource={selectedSource} activeTab={activeTab} handleNav={handleNav} />
        <ProjectsNav repoName={repoName} activeTab={activeTab} handleNav={handleNav} />

        <div className="sidebar-spacer" />

        <SidebarFooter lastEvalStr={lastEvalStr} activeTab={activeTab} handleNav={handleNav} standardsCount={standardsCount} />
      </aside>
    </>
  );
}
