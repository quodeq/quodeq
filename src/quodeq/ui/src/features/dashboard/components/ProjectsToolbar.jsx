import { useState, useEffect, useRef } from 'react';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { t } from '../../../strings/index.js';

// -- Toolbar: name search, filter pills, sync status -----------------------
// Controlled entirely by the `filters` prop -- state lives one level up in
// the nav stack (see actions.onFiltersChange), not here.

// One dropdown filter pill ("location: all ▾"). The first option is the
// default; the pill lights up whenever a non-default value is picked so an
// active filter is visible at a glance. Menu closes on pick, outside
// mousedown, or Escape.
function FilterPill({ label, value, options, valueLabels = {}, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  const display = (v) => valueLabels[v] || v;
  const isSet = value !== options[0];
  return (
    <span className={`projects-filter-pill${isSet ? ' projects-filter-pill--set' : ''}`} ref={rootRef}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {label}: <b>{display(value)}</b> <span className="projects-filter-pill-caret">▾</span>
      </button>
      {open && (
        <div className="projects-filter-pill-menu" role="menu" aria-label={t('projects.filterMenuAria', { label })}>
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              role="menuitemradio"
              aria-checked={opt === value}
              onClick={() => { onChange(opt); setOpen(false); }}
            >
              {display(opt)}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

// "syncing…" while a background refresh is in flight, else "sync failed ·
// retry" when the shared hook reports an error (an initial status/list load
// that never landed -- audit A2; onRefresh doubles as the retry affordance
// since useSharedProjects' refresh() re-checks both status and list), else
// "synced <relative time>" (+ " · stale" when the last refresh failed but a
// prior successful listing is still on screen), or "not synced yet" before
// the first list has EVER landed and there is no error either -- the merged
// list's only sync-status surface now that the old online sub-tab (and its
// "refresh failed, showing results synced..." banner) is gone. Renders
// nothing at all (refresh button included) when no shared repo is
// configured -- there is nothing to sync.
function SyncedIndicator({ configured, lastSynced, stale, error, refreshing, onRefresh }) {
  if (!configured) return null;
  const label = refreshing
    ? t('projects.syncing')
    : error
      ? t('projects.syncFailedRetry')
      : lastSynced == null
        ? t('projects.notSyncedYet')
        : `${t('projects.synced', { time: relativeTime(lastSynced) })}${stale ? ` · ${t('projects.stale')}` : ''}`;
  return (
    <span className="projects-toolbar-sync">
      <span className="projects-toolbar-sync-label">{label}</span>
      <button
        type="button"
        className="projects-page__import-btn"
        aria-label={t('projects.refreshAria')}
        onClick={onRefresh}
        aria-disabled={refreshing || undefined}
      >
        ⟳
      </button>
    </span>
  );
}

export function ProjectsToolbar({ filters = {}, onFiltersChange, configured, lastSynced, stale, error, refreshing, onRefresh }) {
  const { query = '', location = 'all', sort = 'activity' } = filters;
  const set = (patch) => onFiltersChange?.({ query, location, sort, ...patch });
  return (
    <div className="projects-toolbar">
      <input
        type="text"
        className="projects-toolbar-search"
        placeholder={t('projects.searchPlaceholder')}
        aria-label={t('projects.searchAria')}
        value={query}
        onChange={(e) => set({ query: e.target.value })}
      />
      {configured && (
        <FilterPill
          label={t('projects.filterLocation')}
          value={location}
          options={['all', 'local', 'shared']}
          valueLabels={{ all: t('projects.optAll'), local: t('projects.optLocal'), shared: t('projects.optRemote') }}
          onChange={(loc) => set({ location: loc })}
        />
      )}
      <FilterPill
        label={t('projects.filterSort')}
        value={sort}
        options={['activity', 'name', 'score']}
        valueLabels={{ activity: t('projects.optActivity'), name: t('projects.optName'), score: t('projects.optScore') }}
        onChange={(s) => set({ sort: s })}
      />
      <SyncedIndicator configured={configured} lastSynced={lastSynced} stale={stale} error={error} refreshing={refreshing} onRefresh={onRefresh} />
    </div>
  );
}
