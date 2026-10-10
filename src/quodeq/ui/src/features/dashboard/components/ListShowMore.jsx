/**
 * ListShowMore: the footer strip that opens a capped list, the whole strip
 * the button: the count it adds, and "show fewer" once open. Renders nothing
 * when the list already fits.
 */
import { t, LOCALE } from '../../../strings/index.js';

export default function ListShowMore({ open, total, shown, allLabel, onToggle }) {
  if (total <= shown) return null;
  return (
    <button type="button" className="panel-foot list-show-more" onClick={onToggle} aria-expanded={open}>
      {open ? t('overview.showFewer') : allLabel}
      {!open && (
        <span className="list-show-more__hint">
          {t('overview.showMoreHint', { count: (total - shown).toLocaleString(LOCALE) })}
        </span>
      )}
      <span className="list-show-more__chev" aria-hidden="true">{open ? '▴' : '▾'}</span>
    </button>
  );
}
