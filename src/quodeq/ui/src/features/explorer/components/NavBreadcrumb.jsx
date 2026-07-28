import { Fragment, useEffect, useRef, useState } from 'react';
import { collapseCrumbs, isRunDateEntry } from './crumbModel.js';

const PAGE_LABELS = {
  overview: 'overview',
  violations: 'violations',
  map: 'map',
  history: 'history',
  evaluate: 'evaluate',
  standards: 'standards',
  settings: 'settings',
  'grade-formula': 'grade formula',
  projects: 'repositories',
  help: 'help',
};

export function labelFor(entry) {
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
    default:              return entry.label || entry.page;
  }
}

/**
 * NavBreadcrumb — the app's address bar, in the TopBar on desktop.
 *
 * Two navigation ideas at two scales, one rule ("click a segment to move
 * within that level"):
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

  return (
    <nav className="nav-breadcrumb" aria-label="Breadcrumb" ref={rootRef}>
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
                    aria-label="Show hidden path segments"
                    aria-haspopup="menu"
                    aria-expanded={open}
                    onClick={() => setOpenKey(open ? null : 'ellipsis')}
                  >
                    …
                  </button>
                  {open && (
                    <div className="nav-breadcrumb__menu" role="menu" aria-label="Hidden path segments">
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
            return (
              <Fragment key={`${seg.label}-${i}`}>
                {sep}
                <li className={crumbClass}>
                  <button
                    type="button"
                    aria-haspopup="menu"
                    aria-expanded={open}
                    onClick={() => setOpenKey(open ? null : key)}
                  >
                    {seg.label}
                    <span className="nav-breadcrumb__caret" aria-hidden="true">▾</span>
                  </button>
                  {open && (
                    <div className="nav-breadcrumb__menu nav-breadcrumb__menu--siblings" role="menu" aria-label={`Switch ${seg.label}`}>
                      {siblings.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          role="menuitemradio"
                          aria-checked={!!item.current}
                          onClick={() => { setOpenKey(null); if (!item.current) item.onSelect(); }}
                        >
                          <span className="nav-breadcrumb__menu-dot" aria-hidden="true" />
                          {item.label}
                        </button>
                      ))}
                    </div>
                  )}
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
