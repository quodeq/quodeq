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

  describe('coverage line', () => {
    const dateLabel = '13 May 2026';

    // The percentage lives in a child <span>, so the div's text node and the
    // span's text node are separate. Match against the coverage line's full
    // textContent (normalized) to keep these assertions structure-agnostic.
    const coverageLineMatcher = (expectedText) => (_, el) =>
      el?.classList?.contains('dim-gauge-card__coverage-line') &&
      el.textContent.replace(/\s+/g, ' ').trim() === expectedText;

    it('shows "<date> · <pct>%" when filesRead < sourceFileCount', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 850,
            sourceFileCount: 3037,
          }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(coverageLineMatcher(`${dateLabel} · 28%`));
      expect(line).toBeInTheDocument();
      expect(line.getAttribute('title')).toBe(
        'Partial run · 850 of 3,037 files',
      );
    });

    it('appends "stopped: <exitReason>" to the tooltip when exitReason is set', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 850,
            sourceFileCount: 3037,
            exitReason: 'deadline',
          }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(coverageLineMatcher(`${dateLabel} · 28%`));
      expect(line.getAttribute('title')).toBe(
        'Partial run · 850 of 3,037 files · stopped: deadline',
      );
    });

    it('appends "excluded from grade" for a failure_streak (circuit breaker) dimension', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 90,
            sourceFileCount: 100,
            exitReason: 'failure_streak',
          }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(coverageLineMatcher(`${dateLabel} · 90%`));
      expect(line.getAttribute('title')).toBe(
        'Partial run · 90 of 100 files · stopped: failure_streak · excluded from grade',
      );
    });

    it('flags partial when exitReason is "deadline" even if file counts match', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 100,
            sourceFileCount: 100,
            exitReason: 'deadline',
          }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(coverageLineMatcher(`${dateLabel} · 100%`));
      expect(line.getAttribute('title')).toBe(
        'Partial run · 100 of 100 files · stopped: deadline',
      );
    });

    it('shows "<date> · 100%" with no tooltip on a complete run', () => {
      render(
        <DimensionGaugeCard
          item={{
            ...baseItem,
            filesRead: 3037,
            sourceFileCount: 3037,
            exitReason: 'done',
          }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(coverageLineMatcher(`${dateLabel} · 100%`));
      expect(line.getAttribute('title')).toBeNull();
    });

    it('omits the "· %" suffix on legacy runs without file counts', () => {
      render(
        <DimensionGaugeCard
          item={baseItem}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      expect(screen.getByText(dateLabel)).toBeInTheDocument();
      expect(screen.queryByText(/%/)).toBeNull();
    });

    it('builds a tooltip with no file counts when only an exit signal exists', () => {
      render(
        <DimensionGaugeCard
          item={{ ...baseItem, exitReason: 'deadline' }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      const line = screen.getByText(dateLabel);
      expect(line.getAttribute('title')).toBe(
        'Partial run · stopped: deadline',
      );
    });

  });

  describe('unmapped findings', () => {
    const dateLabel = '13 May 2026';
    const coverageLineMatcher = (expectedText) => (_, el) =>
      el?.classList?.contains('dim-gauge-card__coverage-line') &&
      el.textContent.replace(/\s+/g, ' ').trim() === expectedText;

    const renderWith = (extra) =>
      render(
        <DimensionGaugeCard
          item={{ ...baseItem, filesRead: 100, sourceFileCount: 100, ...extra }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );

    it('appends "· N unmapped" after the coverage percentage', () => {
      renderWith({ quarantinedCount: 1 });
      expect(
        screen.getByText(coverageLineMatcher(`${dateLabel} · 100% · 1 unmapped`)),
      ).toBeInTheDocument();
    });

    it('explains the exclusion in a tooltip on the segment itself', () => {
      renderWith({ quarantinedCount: 12 });
      const seg = screen.getByText('12 unmapped');
      expect(seg.getAttribute('title')).toBe(
        '12 findings excluded from scoring: the principle named is not in this dimension\'s standard',
      );
    });

    it('uses the singular noun for one finding', () => {
      renderWith({ quarantinedCount: 1 });
      expect(screen.getByText('1 unmapped').getAttribute('title')).toContain('1 finding excluded');
    });

    it('renders nothing at zero, keeping the pre-existing line shape', () => {
      renderWith({ quarantinedCount: 0 });
      expect(
        screen.getByText(coverageLineMatcher(`${dateLabel} · 100%`)),
      ).toBeInTheDocument();
      expect(screen.queryByText(/unmapped/)).toBeNull();
    });

    it('renders nothing when the field is absent, as on reports written before it existed', () => {
      renderWith({});
      expect(
        screen.getByText(coverageLineMatcher(`${dateLabel} · 100%`)),
      ).toBeInTheDocument();
      expect(screen.queryByText(/unmapped/)).toBeNull();
    });

    it('still shows on a legacy run that has no file counts', () => {
      render(
        <DimensionGaugeCard
          item={{ ...baseItem, quarantinedCount: 3 }}
          dateLabel={dateLabel}
          onDimensionClick={() => {}}
        />,
      );
      expect(
        screen.getByText(coverageLineMatcher(`${dateLabel} · 3 unmapped`)),
      ).toBeInTheDocument();
    });
  });

  describe('partial coverage colouring', () => {
    it('applies the partial CSS class to the coverage % span when exitReason != "done"', () => {
      const item = {
        ...baseItem,
        dateLabel: '23 May 2026',
        filesRead: 8, sourceFileCount: 100,
        exitReason: 'time_limit',
      };
      const { container } = render(<DimensionGaugeCard item={item} onDimensionClick={() => {}} />);
      const pctEl = container.querySelector('.dim-gauge-card__coverage-pct--partial');
      expect(pctEl).not.toBeNull();
    });

    it('does not apply the partial CSS class when exitReason is "done"', () => {
      const item = {
        ...baseItem,
        dateLabel: '23 May 2026',
        filesRead: 100, sourceFileCount: 100,
        exitReason: 'done',
      };
      const { container } = render(<DimensionGaugeCard item={item} onDimensionClick={() => {}} />);
      expect(container.querySelector('.dim-gauge-card__coverage-pct--partial')).toBeNull();
    });
  });
});
