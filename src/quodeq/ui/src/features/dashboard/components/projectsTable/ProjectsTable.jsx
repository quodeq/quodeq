import { useMemo } from 'react';
import { t } from '../../../../strings/index.js';
import { projectIdOrSelf } from '../../../../utils/projectIdentity.js';
import { SORT_KEY, SORT_DIR, sortDirection } from '../../projectsSort.js';
import { LocalProjectRows, SharedProjectRow } from './ProjectRow.jsx';

// The sortable columns, in order; the rest of the header is plain labels.
const SORT_COLUMNS = [
  { key: SORT_KEY.NAME, label: () => t('projects.colProject'), cls: 'projects-row__name' },
  { key: SORT_KEY.SCORE, label: () => t('projects.colScore'), cls: 'projects-row__grade' },
  { key: SORT_KEY.FILES, label: () => t('projects.colFiles'), cls: 'projects-row__num' },
  { key: SORT_KEY.ACTIVITY, label: () => t('projects.colLastRun'), cls: 'projects-row__num' },
];

function SortHeader({ column, filters, onSort }) {
  const active = (filters?.sort ?? SORT_KEY.ACTIVITY) === column.key;
  const dir = sortDirection(filters, column.key);
  const ariaSort = active ? (dir === SORT_DIR.ASC ? 'ascending' : 'descending') : 'none';
  return (
    <div className={column.cls} role="columnheader" aria-sort={ariaSort}>
      <button type="button" className={`projects-table__sort${active ? ' projects-table__sort--on' : ''}`} onClick={() => onSort(column.key)}>
        {column.label()}
        <span className="projects-table__arrow" aria-hidden="true">{active ? (dir === SORT_DIR.ASC ? '↑' : '↓') : ''}</span>
      </button>
    </div>
  );
}

/**
 * The column headers are the sort: clicking one sorts by it, clicking the
 * active one reverses it. Location and sync only show with a server.
 */
export function ProjectsTableHead({ filters, onSort, configured }) {
  return (
    <div className="projects-row projects-row--head" role="row">
      {SORT_COLUMNS.map((column) => <SortHeader key={column.key} column={column} filters={filters} onSort={onSort} />)}
      {configured && <div className="projects-row__location" role="columnheader">{t('projects.colLocation')}</div>}
      {configured && <div className="projects-row__sync" role="columnheader">{t('projects.colSync')}</div>}
      <div className="projects-row__action" role="columnheader"><span className="sr-only">{t('projects.colAction')}</span></div>
      <div className="projects-row__more" role="columnheader" />
    </div>
  );
}

// Parents of the selected subproject get a quiet mark, as the old group did.
function useChildSelectedIds(children, selectedProject) {
  return useMemo(() => {
    const set = new Set();
    for (const [parentId, list] of Object.entries(children || {})) {
      if (list.some((c) => projectIdOrSelf(c) === selectedProject)) set.add(parentId);
    }
    return set;
  }, [children, selectedProject]);
}

export function ProjectsRows({ entries, ctx }) {
  const childSelectedIds = useChildSelectedIds(ctx.children, ctx.selectedProject);
  const rowCtx = { ...ctx, childSelectedIds };
  if (entries.length === 0) return <div className="projects-empty">{t('projects.noMatches')}</div>;
  return entries.map((entry) => (
    entry.local
      ? <LocalProjectRows key={entry.key} entry={entry} ctx={rowCtx} />
      : <SharedProjectRow key={entry.key} entry={entry} ctx={rowCtx} />
  ));
}

/**
 * The frame every state of the page shares: the server band on top (when
 * one is configured), then whatever the page has to show. `narrow` layout is
 * a container query on this frame (see dashboard.css), so a narrow desktop
 * window gets it too.
 */
export function ProjectsTable({ band, configured, children }) {
  return (
    <div className="projects-table-wrap">
      <div className={`projects-table${configured ? ' projects-table--server' : ''}`}>
        {band}
        <div role="table" aria-label={t('projects.tableAria')}>{children}</div>
      </div>
    </div>
  );
}
