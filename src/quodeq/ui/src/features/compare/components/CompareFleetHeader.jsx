import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import ScopePicker from './ScopePicker.jsx';
import DuelTrigger from './DuelTrigger.jsx';
import DimensionTrigger from './DimensionTrigger.jsx';
import { nf } from '../compareFormatters.js';


/** Title + subtitle, and the header controls: duel/dimension launchers and
 * the scope picker. (Ranking lives in the tables' column headers.) */
export default function CompareFleetHeader({
  scopeCount, totalFiles, scoredRows, openDuelPair, openDuel, board, openDimension,
  rows, scopeIds, toggleProject, selectAll, selectFlagged,
  pickerOpen, setPickerOpen,
}) {
  return (
    <div className="term-page-top compare-page__top">
      <TermHeader
        name={t('compare.title')}
        sub={t('compare.subtitle', { count: scopeCount, files: nf(totalFiles) })}
      />
      <div className="term-page-top__controls">
        {openDuelPair && scoredRows.length >= 2 && (
          <DuelTrigger targets={scoredRows} onStart={openDuelPair} openDirect={openDuel} />
        )}
        {board.length > 0 && (
          <DimensionTrigger board={board} onOpen={openDimension} />
        )}
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
