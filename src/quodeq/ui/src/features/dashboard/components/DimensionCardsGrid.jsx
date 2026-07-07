import DimensionGaugeCard from './DimensionGaugeCard.jsx';
import { fallbackDelta } from '../../../utils/dimensionUtils.js';

// Cards keep the incoming (alphabetical) order regardless of the selected
// period: changing the day/week/month re-dims cards but never reorders them,
// so each dimension has a fixed position on the board.
export default function DimensionCardsGrid({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends }) {
  const dimNameSet = selectedDayDimNames instanceof Set ? selectedDayDimNames : new Set();
  return (
    <div className="dimensions-grid">
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
          />
        );
      })}
    </div>
  );
}
