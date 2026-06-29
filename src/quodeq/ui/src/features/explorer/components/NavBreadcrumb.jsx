import { Fragment } from 'react';

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
 * NavBreadcrumb — the app's single breadcrumb bar.
 *
 * Renders as a thin strip under the topbar / right of the sidebar (the
 * AppShell places it directly above page content). Always visible while
 * navigating in a project; falls back to showing just the project root +
 * current tab when the user hasn't drilled in yet.
 *
 * Style: slash-separated plain text, monospace, muted. Intermediate
 * segments are clickable to pop the nav stack; the current segment is
 * accent-colored and non-interactive.
 */
export default function NavBreadcrumb({ stack = [], onGoTo, projectName, onSelectProject }) {
  const crumbs = [];
  if (projectName) crumbs.push({ label: projectName, index: -1, isProject: true });
  stack.forEach((entry, i) => crumbs.push({ label: labelFor(entry), index: i }));

  if (crumbs.length === 0) return null;

  return (
    <nav className="nav-breadcrumb" aria-label="Breadcrumb">
      <ol className="nav-breadcrumb__crumbs">
        {crumbs.map((seg, i) => {
          const isLast = i === crumbs.length - 1;
          // The project root is the persistent indicator: clickable whenever a
          // handler is wired, regardless of position. Other crumbs only pop the
          // nav stack and only when they aren't the current page.
          const isProjectButton = seg.isProject && typeof onSelectProject === 'function';
          const isClickable = isProjectButton || (!isLast && seg.index >= 0);
          const crumbClass = `nav-breadcrumb__crumb${isLast ? ' is-current' : ''}${
            seg.isProject ? ' nav-breadcrumb__crumb--project' : ''
          }`;
          return (
            <Fragment key={`${seg.label}-${i}`}>
              {i > 0 && <li className="nav-breadcrumb__sep" aria-hidden="true">/</li>}
              <li className={crumbClass}>
                {isClickable ? (
                  <button
                    type="button"
                    onClick={() => (seg.isProject ? onSelectProject() : onGoTo(seg.index))}
                  >
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
