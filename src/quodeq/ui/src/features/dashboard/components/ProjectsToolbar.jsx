import { useCallback, useState, useRef } from 'react';
import { t } from '../../../strings/index.js';
import { useDismissOnOutside } from '../../../hooks/useDismissOnOutside.js';

// -- Toolbar: name search, filter pills ------------------------------------
// The team repository's sync status lives in the strip above (SyncStrip).
// Controlled entirely by the `filters` prop -- state lives one level up in
// the nav stack (see actions.onFiltersChange), not here.

// One dropdown filter pill ("location: all ▾"). The first option is the
// default; the pill lights up whenever a non-default value is picked so an
// active filter is visible at a glance. Menu closes on pick, outside
// mousedown, or Escape.
function FilterPill({ label, value, options, valueLabels = {}, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  useDismissOnOutside(open, rootRef, useCallback(() => setOpen(false), []));
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

export function ProjectsToolbar({ filters = {}, onFiltersChange, configured }) {
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
    </div>
  );
}
