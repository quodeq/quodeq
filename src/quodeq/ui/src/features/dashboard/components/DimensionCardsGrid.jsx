import { useMemo } from 'react';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';

function computeDelta(item) {
  const curr = parseFloat(item.overallScore);
  const prev = parseFloat(item.previousScore);
  return !Number.isNaN(curr) && !Number.isNaN(prev) ? curr - prev : null;
}

export default function DimensionCardsGrid({ sortedDimensions, onDimensionClick, selectedDayDimNames }) {
  const dimNameSet = selectedDayDimNames instanceof Set ? selectedDayDimNames : new Set();
  const sorted = useMemo(() => [...sortedDimensions].sort((a, b) => {
    if (dimNameSet.size === 0) return a.dimension.localeCompare(b.dimension);
    const aActive = dimNameSet.has((a.dimension || '').toLowerCase());
    const bActive = dimNameSet.has((b.dimension || '').toLowerCase());
    if (aActive && !bActive) return -1;
    if (!aActive && bActive) return 1;
    return a.dimension.localeCompare(b.dimension);
  }), [sortedDimensions, dimNameSet]);

  return (
    <div className="dimensions-grid">
      {sorted.map((item) => {
        const isActive = dimNameSet.size === 0 || dimNameSet.has((item.dimension || '').toLowerCase());
        return (
          <DimensionGaugeCard
            key={item.dimension}
            item={item}
            delta={computeDelta(item)}
            onDimensionClick={onDimensionClick}
            evaluatedToday={isActive}
          />
        );
      })}
    </div>
  );
}
