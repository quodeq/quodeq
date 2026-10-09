import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import NotEvaluatedGaugeCard from './NotEvaluatedGaugeCard.jsx';
import { fallbackDelta } from '../../../utils/dimensionUtils.js';
import { EVIDENCE_CONFIDENCE } from '../../../vocab/evidenceConfidence.js';
import { useBalancedColumns } from '../hooks/useBalancedColumns.js';

// Narrowest card that still fits a long name ("clean-architecture") on one
// line, and the grid's gap (--space-3).
const CARD_MIN_WIDTH = 180;
const GRID_GAP = 12;

// Cards keep the incoming (alphabetical) order regardless of the selected
// period: changing the day/week/month re-dims cards but never reorders them,
// so each dimension has a fixed position on the board. Standards switched on
// but never evaluated follow as empty cards. Rows are balanced (5 + 4, never
// 8 + 1) once the grid needs more than one.
export default function DimensionCardsGrid({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends, notEvaluated = [], onEvaluate }) {
  const dimNameSet = selectedDayDimNames instanceof Set ? selectedDayDimNames : new Set();
  const [gridRef, gridStyle] = useBalancedColumns(sortedDimensions.length + notEvaluated.length, CARD_MIN_WIDTH, GRID_GAP);
  return (
    <div className="dimensions-grid" ref={gridRef} style={gridStyle}>
      {sortedDimensions.map((item) => {
        const isActive = dimNameSet.size === 0 || dimNameSet.has((item.dimension || '').toLowerCase());
        const entry = dimTrends?.[(item.dimension || '').toLowerCase()];
        const delta = entry ? entry.delta : fallbackDelta(item);
        return (
          <DimensionGaugeCard
            key={item.dimension}
            item={item}
            delta={delta}
            onDimensionClick={onDimensionClick}
            evaluatedToday={isActive}
            thinEvidence={item.confidence === EVIDENCE_CONFIDENCE.LOW}
          />
        );
      })}
      {notEvaluated.map((name) => <NotEvaluatedGaugeCard key={name} name={name} onActivate={onEvaluate} />)}
    </div>
  );
}
