/**
 * CompareFleetView: the Compare tab's landing view, an overview of the
 * projects in scope for a manager's first glance and an analyst's second:
 *
 *   summary strip      where the fleet stands, in six numbers
 *   projects table     ranked on a shared axis, exposure per size
 *   score matrix       every project against every dimension
 *   direction map      score against 30-day movement | needs attention
 *   dimension health   grade mix per dimension, weakest first
 *
 * One hover state links the table, the map and the attention list: point
 * at a project anywhere and it lights up everywhere.
 */
import { useMemo, useState } from 'react';
import CompareFleetHeader from './CompareFleetHeader.jsx';
import CompareFleetKpis from './CompareFleetKpis.jsx';
import CompareFleetTable from './CompareFleetTable.jsx';
import CompareFleetMatrix from './CompareFleetMatrix.jsx';
import CompareDirectionMap from './CompareDirectionMap.jsx';
import CompareAttentionList from './CompareAttentionList.jsx';
import CompareDimensionHealth from './CompareDimensionHealth.jsx';
import ComparePanel from './ComparePanel.jsx';
import { t } from '../../../strings/index.js';
import { CONSEQUENCE_LEVEL } from '../compareFleet.js';

// Top-N by consequence always shown in the attention list; beyond that
// only rows that actually flag ('watch'+) qualify.
const ATTENTION_LEAD_COUNT = 3;

/**
 * Row partitioning:
 *   - scoredRows: everything with numbers to show.
 *   - attnAll: the attention list (top 3 by consequence, then flagged rows).
 *   - pending: rows still computing or failed to load (listed, no numbers).
 *   - unevaluated: never-evaluated projects (settled, no data, no error),
 *     collapsed into one line.
 */
function partitionFleetRows(orderedRows, attention, errorsById) {
  const scoredRows = orderedRows.filter((r) => r.hasData);
  const attnAll = [
    ...attention.slice(0, ATTENTION_LEAD_COUNT),
    ...attention.slice(ATTENTION_LEAD_COUNT).filter((a) => a.level !== CONSEQUENCE_LEVEL.CLEAR),
  ];
  const isUnevaluated = (row) => row.loaded && !row.hasData && !errorsById[row.id];
  const pending = orderedRows.filter((row) => !row.hasData && !isUnevaluated(row));
  const unevaluated = orderedRows.filter(isUnevaluated);
  return { scoredRows, attnAll, pending, unevaluated };
}

export default function CompareFleetView({
  rows, orderedRows, fleet, board, attention, errorsById,
  pickerOpen, setPickerOpen, scopeIds, scopeCount,
  toggleProject, selectAll, selectFlagged, openDimension, openDuel, openDuelPair, onOpenProject,
  onOpenProjectDimension,
}) {
  const [hover, setHover] = useState(null);
  // Memoised so a hover (a re-render of this view) hands the charts the
  // same row arrays, and their own memoised geometry is not rebuilt.
  const { scoredRows, attnAll, pending, unevaluated } = useMemo(
    () => partitionFleetRows(orderedRows, attention, errorsById),
    [orderedRows, attention, errorsById],
  );
  const linked = { hover, setHover, onOpenProject };

  return (
    <>
      <CompareFleetHeader
        scopeCount={scopeCount} totalFiles={fleet.totalFiles} scoredRows={scoredRows}
        openDuelPair={openDuelPair} openDuel={openDuel} board={board} openDimension={openDimension}
        rows={rows} scopeIds={scopeIds}
        toggleProject={toggleProject} selectAll={selectAll} selectFlagged={selectFlagged}
        pickerOpen={pickerOpen} setPickerOpen={setPickerOpen}
      />
      {scoredRows.length > 0 && <CompareFleetKpis rows={scoredRows} fleet={fleet} />}
      <CompareFleetTable
        scoredRows={scoredRows} pending={pending} unevaluated={unevaluated} errorsById={errorsById}
        fleetScore={fleet.score} {...linked}
      />
      {scoredRows.length > 0 && (
        <>
          <CompareFleetMatrix
            rows={scoredRows} board={board} fleetScore={fleet.score}
            onOpenProject={onOpenProject} onOpenProjectDimension={onOpenProjectDimension}
          />
          <div className="compare-fleet__pair">
            {/* The map needs width and hover: a phone keeps the attention list. */}
            <div className="compare-fleet__desktop">
              <ComparePanel ariaLabel={t('compare.mapAria')} header={t('compare.mapHeader')} note={t('compare.mapNote')}>
                <CompareDirectionMap rows={scoredRows} fleetScore={fleet.score} {...linked} />
              </ComparePanel>
            </div>
            <CompareAttentionList items={attnAll} onOpenProjectDimension={onOpenProjectDimension} {...linked} />
          </div>
          <CompareDimensionHealth board={board} openDimension={openDimension} />
        </>
      )}
    </>
  );
}
