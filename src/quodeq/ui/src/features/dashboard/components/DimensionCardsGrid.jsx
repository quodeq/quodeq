import { useMemo } from 'react';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';

// Fallback delta when the parent did not supply a period-aware entry for this
// dimension (defensive; the accumulated overview always supplies dimTrends).
function fallbackDelta(item) {
  const curr = parseFloat(item.overallScore);
  const prev = parseFloat(item.previousScore);
  return !Number.isNaN(curr) && !Number.isNaN(prev) ? curr - prev : null;
}

export default function DimensionCardsGrid({ sortedDimensions, onDimensionClick, selectedDayDimNames, dimTrends }) {
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
