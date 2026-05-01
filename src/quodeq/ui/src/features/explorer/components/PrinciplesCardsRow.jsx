import DimensionGaugeCard from '../../dashboard/components/DimensionGaugeCard.jsx';

/**
 * Renders one DimensionGaugeCard per principle. Adapts a principleGrade-style
 * record into the `item` shape DimensionGaugeCard expects, and surfaces the
 * "Insufficient" grade as the `isInsufficient` state.
 */
function principleToItem(p) {
  const violationCount = p.violationCount ?? 0;
  const complianceCount = p.complianceCount ?? 0;
  return {
    dimension: p.principle,
    overallScore: p.score ?? null,
    totals: {
      violationCount,
      complianceCount,
      severity: p.severity || {},
    },
  };
}

export default function PrinciplesCardsRow({ principles = [], onPrincipleClick }) {
  return (
    <div className="qd-cards-row">
      {principles.map((p) => {
        const isInsufficient = (p.grade || '').toLowerCase() === 'insufficient';
        const item = principleToItem(p);
        return (
          <DimensionGaugeCard
            key={p.principle}
            item={item}
            isInsufficient={isInsufficient}
            onDimensionClick={() => onPrincipleClick?.(p.principle)}
          />
        );
      })}
    </div>
  );
}
