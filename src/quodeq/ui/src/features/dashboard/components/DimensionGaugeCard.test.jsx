import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';

const baseItem = {
  dimension: 'modifiability',
  overallScore: '4.7',
  totals: { violationCount: 116, complianceCount: 232, severity: { critical: 0, major: 11, minor: 105 } },
};

describe('DimensionGaugeCard', () => {
  it('renders a normal gauge with score and grade', () => {
    render(<DimensionGaugeCard item={baseItem} onDimensionClick={() => {}} />);
    expect(screen.getByText('4.7')).toBeInTheDocument();
    expect(screen.getByText(/VIOL/)).toBeInTheDocument();
  });

  it('renders an insufficient state when isInsufficient=true', () => {
    render(
      <DimensionGaugeCard
        item={{ dimension: 'analyzability', overallScore: null }}
        isInsufficient
        onDimensionClick={() => {}}
      />,
    );
    expect(screen.getByText('—')).toBeInTheDocument();
    // The SVG grade text shows the uppercase word INSUFFICIENT
    expect(screen.getByText('INSUFFICIENT')).toBeInTheDocument();
    // The caption below the gauge shows the lowercase phrase
    expect(screen.getByText('insufficient evidence')).toBeInTheDocument();
    // No VIOL meta line in insufficient state
    expect(screen.queryByText(/VIOL/)).toBeNull();
  });

  describe('partial badge', () => {
    it("shows 'Partial — N of M files (P%)' when filesRead < sourceFileCount", () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 850,
            sourceFileCount: 3037,
          }}
          onDimensionClick={() => {}}
        />,
      );
      const badge = screen.getByText(/Partial/i);
      expect(badge).toBeInTheDocument();
      expect(badge.textContent).toMatch(/850/);
      expect(badge.textContent).toMatch(/3,?037/);
      expect(badge.textContent).toMatch(/28%/);
    });

    it("shows the badge when exitReason is 'deadline' even if file counts match", () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 100,
            sourceFileCount: 100,
            exitReason: 'deadline',
          }}
          onDimensionClick={() => {}}
        />,
      );
      expect(screen.getByText(/Partial/i)).toBeInTheDocument();
    });

    it('does NOT show the badge when filesRead equals sourceFileCount and exitReason is null', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 3037,
            sourceFileCount: 3037,
            exitReason: null,
          }}
          onDimensionClick={() => {}}
        />,
      );
      expect(screen.queryByText(/Partial/i)).not.toBeInTheDocument();
    });

    it('does NOT show the badge when neither filesRead nor exitReason is present (legacy run)', () => {
      render(<DimensionGaugeCard item={baseItem} onDimensionClick={() => {}} />);
      expect(screen.queryByText(/Partial/i)).not.toBeInTheDocument();
    });
  });
});
