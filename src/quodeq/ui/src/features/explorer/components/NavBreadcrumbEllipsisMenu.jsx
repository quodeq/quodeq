import { t } from '../../../strings/index.js';

/** The "…" chip that opens the hidden (collapsed-middle) ancestors as a
 * plain list — an ancestor menu is a path, not a choice. */
export default function NavBreadcrumbEllipsisMenu({ seg, sep, open, setOpenKey, goTo }) {
  return (
    <>
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
    </>
  );
}
