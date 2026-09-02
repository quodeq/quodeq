import { useEffect, useRef } from 'react';
import { scoreColorClass } from '../../../utils/formatters.js';
import { t, LOCALE } from '../../../strings/index.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function ScopePickerRow({ row, on, toggleProject }) {
  return (
    <li>
      <label className="compare-picker__row">
        <input
          type="checkbox"
          checked={on}
          onChange={() => toggleProject(row.id)}
        />
        <span className="compare-picker__name">
          {row.name}
          {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
        </span>
        <span
          className={`compare-picker__score ${scoreColorClass(row.score)}`}
        >
          {score1(row.score)}
        </span>
        <span className="compare-picker__viol">
          {row.hasData ? t('compare.violCount', { count: nf(row.totalViolations) }) : '—'}
        </span>
      </label>
    </li>
  );
}

function ScopePickerPopover({ rows, scopeIds, toggleProject, selectAll, selectFlagged }) {
  return (
    <div className="compare-picker__pop">
      <div className="compare-picker__head">
        <span className="compare-picker__title">{t('compare.pickerTitle')}</span>
        <button type="button" className="compare-picker__quick" onClick={selectAll}>
          {t('compare.pickerAll')}
        </button>
        <button type="button" className="compare-picker__quick" onClick={selectFlagged}>
          {t('compare.pickerFlagged')}
        </button>
      </div>
      <ul className="compare-picker__list">
        {rows.map((row) => (
          <ScopePickerRow
            key={row.id}
            row={row}
            on={scopeIds == null || scopeIds.includes(row.id)}
            toggleProject={toggleProject}
          />
        ))}
      </ul>
    </div>
  );
}

export default function ScopePicker({
  rows, scopeIds, toggleProject, selectAll, selectFlagged, pickerOpen, setPickerOpen, scopeCount,
}) {
  // Dismiss like every other popover in the app (NavBreadcrumb's pattern):
  // a press anywhere outside, or Escape, closes it.
  const rootRef = useRef(null);
  useEffect(() => {
    if (!pickerOpen) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setPickerOpen(false); };
    const onEsc = (e) => { if (e.key === 'Escape') setPickerOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
  }, [pickerOpen, setPickerOpen]);

  const allSelected = scopeIds == null || scopeCount === rows.length;
  const label = allSelected
    ? t('compare.scopeAll', { count: rows.length })
    : t('compare.scopeSome', { selected: scopeCount, count: rows.length });
  return (
    <span className="compare-picker" ref={rootRef}>
      <button
        type="button"
        className={`compare-picker__toggle${allSelected ? '' : ' compare-picker__toggle--filtered'}`}
        onClick={() => setPickerOpen(!pickerOpen)}
        aria-expanded={pickerOpen}
      >
        {label}
        <span className="compare-picker__glyph" aria-hidden="true">{pickerOpen ? '▲' : '▼'}</span>
      </button>
      {pickerOpen && (
        <ScopePickerPopover
          rows={rows}
          scopeIds={scopeIds}
          toggleProject={toggleProject}
          selectAll={selectAll}
          selectFlagged={selectFlagged}
        />
      )}
    </span>
  );
}
