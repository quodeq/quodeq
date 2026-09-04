import { Fragment, useRef, useState } from 'react';
import { collapseCrumbs, isRunDateEntry } from './crumbModel.js';
import { useBreadcrumbDismiss } from './useBreadcrumbDismiss.js';
import { useHoldToOpen } from './useHoldToOpen.js';
import NavBreadcrumbEllipsisMenu from './NavBreadcrumbEllipsisMenu.jsx';
import NavBreadcrumbSegmentMenu from './NavBreadcrumbSegmentMenu.jsx';
import { t } from '../../../strings/index.js';

const PAGE_LABELS = {
  overview: t('explorer.overviewCrumb'),
  violations: t('explorer.violationsCrumb'),
  map: t('explorer.mapCrumb'),
  history: t('explorer.historyCrumb'),
  evaluate: t('explorer.evaluateCrumb'),
  standards: t('explorer.standardsCrumb'),
  settings: t('explorer.settingsCrumb'),
  'grade-formula': t('explorer.crumbGradeFormula'),
  projects: t('explorer.projectsCrumb'),
  help: t('explorer.helpCrumb'),
};

export function labelFor(entry) {
  // A map drill-down entry carries its folder path (see App.jsx's map
  // renderer): the crumb shows the folder name, so the trail reads
  // map / src / components. The root map entry (no path) falls through to
  // its tab label.
  if (entry.page === 'map' && entry.path) {
    return entry.path.split('/').filter(Boolean).pop() || t('explorer.mapCrumb');
  }
  if (PAGE_LABELS[entry.page]) return PAGE_LABELS[entry.page];
  switch (entry.page) {
    case 'run':           return entry.label || entry.runId || t('explorer.runFallback');
    case 'history-run':   return entry.dateLabel || entry.runId || t('explorer.runFallback');
    case 'explorer':      return entry.dimension
      ? entry.dimension.toLowerCase()
      : t('explorer.dimensionFallback');
    case 'violation':     return entry.label || entry.principle?.name || t('explorer.violationFallback');
    case 'file':          return entry.label || entry.file?.path || t('explorer.fileFallback');
    case 'principle':     return entry.label || t('explorer.principleFallback');
    case 'evalprinciple': return entry.label || entry.principleName || t('explorer.principleFallback');
    case 'finding':       return entry.label || t('explorer.findingFallback');
    // Fleet entry reads "compare"; a drill-down entry carries its dimension
    // so the crumb trail reads compare › security, and a head-to-head entry
    // reads compare › duel.
    case 'compare':       return entry.duel
      ? t('compare.crumbDuel')
      : entry.dimension ? entry.dimension.toLowerCase() : t('explorer.compareFallback');
    default:              return entry.label || entry.page;
  }
}

/** Build the crumb list: project root (if any) + one entry per stack level. */
function buildCrumbs(stack, projectName) {
  const crumbs = [];
  if (projectName) crumbs.push({ label: projectName, index: -1, isProject: true });
  stack.forEach((entry, i) => crumbs.push({
    label: labelFor(entry),
    index: i,
    entry,
    isRunDate: isRunDateEntry(entry),
  }));
  return crumbs;
}

/** One rendered segment: the ellipsis chip, a sibling-menu segment, or a
 * plain (possibly clickable) crumb. */
function BreadcrumbSegment({ seg, sep, isLast, siblingsFor, openKey, setOpenKey, goTo, onGoTo, holder, onSelectProject }) {
  if (seg.ellipsis) {
    return (
      <NavBreadcrumbEllipsisMenu
        seg={seg} sep={sep} open={openKey === 'ellipsis'} setOpenKey={setOpenKey} goTo={goTo}
      />
    );
  }

  const siblings = seg.entry && siblingsFor ? siblingsFor(seg.entry, seg.index) : null;
  const hasMenu = Array.isArray(siblings) && siblings.length > 1;
  const crumbClass = `nav-breadcrumb__crumb${isLast ? ' is-current' : ''}${
    seg.isProject ? ' nav-breadcrumb__crumb--project' : ''
  }${hasMenu ? ' nav-breadcrumb__crumb--menu' : ''}`;

  if (hasMenu) {
    const menuKey = `seg-${seg.index}`;
    return (
      <NavBreadcrumbSegmentMenu
        seg={seg} sep={sep} isLast={isLast} siblings={siblings} crumbClass={crumbClass}
        open={openKey === menuKey} menuKey={menuKey} setOpenKey={setOpenKey} onGoTo={onGoTo} goTo={goTo}
        consumeHold={holder.consumeHold} startHold={holder.startHold} cancelHold={holder.cancelHold}
      />
    );
  }

  // The project root is the persistent indicator: clickable whenever a
  // handler is wired, regardless of position. Other crumbs only pop the
  // nav stack and only when they aren't the current page.
  const isProjectButton = seg.isProject && typeof onSelectProject === 'function';
  const isClickable = isProjectButton || (!isLast && seg.index >= 0);
  return (
    <>
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
    </>
  );
}

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
  useBreadcrumbDismiss(openKey, setOpenKey, rootRef);
  const holder = useHoldToOpen(setOpenKey);

  const crumbs = buildCrumbs(stack, projectName);
  if (crumbs.length === 0) return null;

  const display = collapseCrumbs(crumbs);
  const lastCrumb = crumbs[crumbs.length - 1];

  const goTo = (seg) => {
    setOpenKey(null);
    if (seg.isProject) onSelectProject?.();
    else onGoTo(seg.index);
  };

  return (
    <nav className="nav-breadcrumb" aria-label={t('explorer.breadcrumb')} ref={rootRef}>
      <ol className="nav-breadcrumb__crumbs">
        {display.map((seg, i) => {
          const sep = i > 0 && <li className="nav-breadcrumb__sep" aria-hidden="true">/</li>;
          return (
            <Fragment key={seg.ellipsis ? 'ellipsis' : `${seg.label}-${i}`}>
              <BreadcrumbSegment
                seg={seg} sep={sep} isLast={seg === lastCrumb} siblingsFor={siblingsFor}
                openKey={openKey} setOpenKey={setOpenKey} goTo={goTo} onGoTo={onGoTo}
                holder={holder} onSelectProject={onSelectProject}
              />
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
