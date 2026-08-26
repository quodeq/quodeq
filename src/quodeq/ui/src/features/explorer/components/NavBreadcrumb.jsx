import { Fragment, useEffect, useRef, useState } from 'react';
import { collapseCrumbs, isRunDateEntry } from './crumbModel.js';
import { t } from '../../../strings/index.js';

const PAGE_LABELS = {
  overview: 'overview',
  violations: 'violations',
  map: 'map',
  history: 'history',
  evaluate: 'evaluate',
  standards: 'standards',
  settings: 'settings',
  'grade-formula': t('explorer.crumbGradeFormula'),
  projects: 'repositories',
  help: 'help',
};

export function labelFor(entry) {
  // A map drill-down entry carries its folder path (see App.jsx's map
  // renderer): the crumb shows the folder name, so the trail reads
  // map / src / components. The root map entry (no path) falls through to
  // its tab label.
  if (entry.page === 'map' && entry.path) {
    return entry.path.split('/').filter(Boolean).pop() || 'map';
  }
  if (PAGE_LABELS[entry.page]) return PAGE_LABELS[entry.page];
  switch (entry.page) {
    case 'run':           return entry.label || entry.runId || 'run';
    case 'history-run':   return entry.dateLabel || entry.runId || 'run';
    case 'explorer':      return entry.dimension
      ? entry.dimension.toLowerCase()
      : 'dimension';
    case 'violation':     return entry.label || entry.principle?.name || 'violation';
    case 'file':          return entry.label || entry.file?.path || 'file';
    case 'principle':     return entry.label || 'principle';
    case 'evalprinciple': return entry.label || entry.principleName || 'principle';
    case 'finding':       return entry.label || 'finding';
    // Fleet entry reads "compare"; a drill-down entry carries its dimension
    // so the crumb trail reads compare › security, and a head-to-head entry
    // reads compare › duel.
    case 'compare':       return entry.duel
      ? t('compare.crumbDuel')
      : entry.dimension ? entry.dimension.toLowerCase() : 'compare';
    default:              return entry.label || entry.page;
  }
}

// How long a pointer must stay down on an earlier segment before the
// sibling menu opens instead of navigating (mirrors browser back-button
// press-and-hold).
const HOLD_TO_OPEN_MS = 450;

/**
 * NavBreadcrumb — the app's address bar, in the TopBar on desktop.
 *
 * Two navigation ideas at two scales, one rule per position:
 *   - an EARLIER segment navigates back to its level on click, like an
 *     address bar; its sibling menu opens from the caret, a right-click,
 *     or press-and-hold (the browser back-button convention);
 *   - the CURRENT segment has no back target, so click keeps opening the
 *     jump menu.
 * Plus:
 *   - collapse-the-middle: deep paths keep the two ends that matter (project
 *     root and where you are); hidden ancestors sit one click away behind a
 *     "…" chip that opens them as a plain list (see crumbModel.js);
 *   - jump bar: a segment whose siblings are known (`siblingsFor`) opens a
 *     menu of them with the current one marked, so lateral moves don't
 *     require walking back up.
 * Ancestor menus are a path, sibling menus are a choice — they're styled
 * differently on purpose.
 *
 * Segments never wrap; only the current (last) segment may shrink.
 */
export default function NavBreadcrumb({ stack = [], onGoTo, projectName, onSelectProject, siblingsFor }) {
  const [openKey, setOpenKey] = useState(null);
  const rootRef = useRef(null);

  useEffect(() => {
    if (openKey == null) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpenKey(null); };
    const onEsc = (e) => { if (e.key === 'Escape') setOpenKey(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
  }, [openKey]);

  const crumbs = [];
  if (projectName) crumbs.push({ label: projectName, index: -1, isProject: true });
  stack.forEach((entry, i) => crumbs.push({
    label: labelFor(entry),
    index: i,
    entry,
    isRunDate: isRunDateEntry(entry),
  }));

  if (crumbs.length === 0) return null;

  const display = collapseCrumbs(crumbs);
  const lastCrumb = crumbs[crumbs.length - 1];

  const goTo = (seg) => {
    setOpenKey(null);
    if (seg.isProject) onSelectProject?.();
    else onGoTo(seg.index);
  };

  // Press-and-hold on an earlier jump-bar segment opens its sibling menu
  // (the browser back-button convention); a released hold must then swallow
  // the click that follows the pointerup so it doesn't also navigate.
  const holdTimer = useRef(null);
  const holdFired = useRef(false);
  useEffect(() => () => clearTimeout(holdTimer.current), []);
  const startHold = (key) => {
    holdFired.current = false;
    clearTimeout(holdTimer.current);
    holdTimer.current = setTimeout(() => {
      holdFired.current = true;
      setOpenKey(key);
    }, HOLD_TO_OPEN_MS);
  };
  const cancelHold = () => clearTimeout(holdTimer.current);
  const consumeHold = () => {
    const fired = holdFired.current;
    holdFired.current = false;
    return fired;
  };

  return (
    <nav className="nav-breadcrumb" aria-label={t('explorer.breadcrumb')} ref={rootRef}>
      <ol className="nav-breadcrumb__crumbs">
        {display.map((seg, i) => {
          const sep = i > 0 && <li className="nav-breadcrumb__sep" aria-hidden="true">/</li>;

          if (seg.ellipsis) {
            const open = openKey === 'ellipsis';
            return (
              <Fragment key="ellipsis">
                {sep}
                <li className="nav-breadcrumb__crumb nav-breadcrumb__crumb--ellipsis">
                  <button
                    type="button"
                    aria-label={t('explorer.showHiddenSegments')}
                    aria-haspopup="menu"
                    aria-expanded={open}
                    onClick={() => setOpenKey(open ? null : 'ellipsis')}
                  >
                    …
                  </button>
                  {open && (
                    <div className="nav-breadcrumb__menu" role="menu" aria-label={t('explorer.hiddenSegments')}>
                      {seg.hidden.map((h) => (
                        <button
                          key={`${h.label}-${h.index}`}
                          type="button"
                          role="menuitem"
                          onClick={() => goTo(h)}
                        >
                          {h.label}
                        </button>
                      ))}
                    </div>
                  )}
                </li>
              </Fragment>
            );
          }

          const isLast = seg === lastCrumb;
          const siblings = seg.entry && siblingsFor ? siblingsFor(seg.entry, seg.index) : null;
          const hasMenu = Array.isArray(siblings) && siblings.length > 1;
          const crumbClass = `nav-breadcrumb__crumb${isLast ? ' is-current' : ''}${
            seg.isProject ? ' nav-breadcrumb__crumb--project' : ''
          }${hasMenu ? ' nav-breadcrumb__crumb--menu' : ''}`;

          if (hasMenu) {
            const key = `seg-${seg.index}`;
            const open = openKey === key;
            const toggleMenu = () => setOpenKey(open ? null : key);
            const menu = open && (
              <div className="nav-breadcrumb__menu nav-breadcrumb__menu--siblings" role="menu" aria-label={`Switch ${seg.label}`}>
                {siblings.map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    role="menuitemradio"
                    aria-checked={!!item.current}
                    // Picking the current sibling means "back to this level".
                    // onGoTo no-ops when this is already the last entry.
                    onClick={() => { setOpenKey(null); if (item.current) onGoTo(seg.index); else item.onSelect(); }}
                  >
                    <span className="nav-breadcrumb__menu-dot" aria-hidden="true" />
                    {item.label}
                  </button>
                ))}
              </div>
            );

            if (isLast) {
              // Current level: there is no "back" target, so a plain click
              // keeps opening the jump menu.
              return (
                <Fragment key={`${seg.label}-${i}`}>
                  {sep}
                  <li className={crumbClass}>
                    <button
                      type="button"
                      aria-haspopup="menu"
                      aria-expanded={open}
                      onClick={toggleMenu}
                    >
                      {seg.label}
                      <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
                    </button>
                    {menu}
                  </li>
                </Fragment>
              );
            }

            // Earlier level: click walks back like an address bar; the
            // sibling menu opens from the caret button, a right-click, or a
            // press-and-hold.
            return (
              <Fragment key={`${seg.label}-${i}`}>
                {sep}
                <li className={crumbClass}>
                  <button
                    type="button"
                    onClick={() => { if (consumeHold()) return; goTo(seg); }}
                    onContextMenu={(e) => { e.preventDefault(); setOpenKey(key); }}
                    onPointerDown={() => startHold(key)}
                    onPointerUp={cancelHold}
                    onPointerLeave={cancelHold}
                    onPointerCancel={cancelHold}
                  >
                    {seg.label}
                  </button>
                  <button
                    type="button"
                    className="nav-breadcrumb__caret-btn"
                    aria-label={`Switch ${seg.label}`}
                    aria-haspopup="menu"
                    aria-expanded={open}
                    onClick={toggleMenu}
                  >
                    <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
                  </button>
                  {menu}
                </li>
              </Fragment>
            );
          }

          // The project root is the persistent indicator: clickable whenever a
          // handler is wired, regardless of position. Other crumbs only pop the
          // nav stack and only when they aren't the current page.
          const isProjectButton = seg.isProject && typeof onSelectProject === 'function';
          const isClickable = isProjectButton || (!isLast && seg.index >= 0);
          return (
            <Fragment key={`${seg.label}-${i}`}>
              {sep}
              <li className={crumbClass}>
                {isClickable ? (
                  <button type="button" onClick={() => goTo(seg)}>
                    {seg.label}
                  </button>
                ) : (
                  <span>{seg.label}</span>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
