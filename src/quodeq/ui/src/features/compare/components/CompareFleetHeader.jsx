import { TermHeader } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import ScopePicker from './ScopePicker.jsx';
import DuelTrigger from './DuelTrigger.jsx';
import DimensionTrigger from './DimensionTrigger.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));

/** Title + subtitle, and the header controls: duel/dimension launchers,
 * the sort toggle, and the scope picker. */
export default function CompareFleetHeader({
  scopeCount, totalFiles, scoredRows, openDuelPair, openDuel, board, openDimension,
  sortDir, toggleSortDir, rows, scopeIds, toggleProject, selectAll, selectFlagged,
  pickerOpen, setPickerOpen,
}) {
  return (
    <div className="compare-page__top">
      <TermHeader
        name={t('compare.title')}
        sub={t('compare.subtitle', { count: scopeCount, files: nf(totalFiles) })}
      />
      <div className="compare-header__controls">
        {openDuelPair && scoredRows.length >= 2 && (
          <DuelTrigger targets={scoredRows} onStart={openDuelPair} openDirect={openDuel} />
        )}
        {board.length > 0 && (
          <DimensionTrigger board={board} onOpen={openDimension} />
        )}
        <span className="compare-sort" role="group" aria-label={t('compare.sortAria')}>
          <button
            type="button"
            className="compare-sort__btn compare-sort__btn--on"
            onClick={toggleSortDir}
            aria-label={t('compare.sortToggleAria')}
          >
            {t('compare.sortScore')} {sortDir === 'desc' ? '↓' : '↑'}
          </button>
        </span>
        <ScopePicker
          rows={rows}
          scopeIds={scopeIds}
          scopeCount={scopeCount}
          toggleProject={toggleProject}
          selectAll={selectAll}
          selectFlagged={selectFlagged}
          pickerOpen={pickerOpen}
          setPickerOpen={setPickerOpen}
        />
      </div>
    </div>
  );
}
