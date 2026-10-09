import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import CompareDuelTrend from './CompareDuelTrend.jsx';

const NOW = Date.parse('2026-03-01T00:00:00.000Z');

describe('CompareDuelTrend: degenerate input', () => {
  it('renders nothing when both series are empty', () => {
    const { container } = render(<CompareDuelTrend a={[]} b={[]} aName="Alpha" bName="Beta" now={NOW} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('drops an unparseable run instead of poisoning the chart with NaN', () => {
    const a = [{ dateISO: 'not-a-date', value: 7 }, { dateISO: '2026-02-01T00:00:00.000Z', value: 7.5 }];
    const b = [{ dateISO: '2026-01-15T00:00:00.000Z', value: 6 }];
    const { container } = render(<CompareDuelTrend a={a} b={b} aName="Alpha" bName="Beta" now={NOW} />);
    expect(container.querySelector('svg')).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/NaN|Infinity/);
  });
});

describe('CompareDuelTrend: drawing', () => {
  const a = [
    { dateISO: '2026-01-01T00:00:00.000Z', value: 6 },
    { dateISO: '2026-02-01T00:00:00.000Z', value: 8 },
  ];
  const b = [
    { dateISO: '2026-01-05T00:00:00.000Z', value: 5 },
    { dateISO: '2026-02-10T00:00:00.000Z', value: 5.5 },
  ];

  it('draws a smoothed line and the faint real runs per side, labelled with the real latest score', () => {
    const { container } = render(<CompareDuelTrend a={a} b={b} aName="Alpha" bName="Beta" now={NOW} />);
    expect(container.querySelectorAll('.compare-duel-trend__line')).toHaveLength(2);
    expect(container.querySelectorAll('.compare-duel-trend__raw')).toHaveLength(2);
    expect(container.querySelector('.compare-duel-trend__end--a')).toHaveTextContent('8.0');
    expect(container.querySelector('.compare-duel-trend__end--b')).toHaveTextContent('5.5');
  });

  it('tints the gap by the leader', () => {
    const { container } = render(<CompareDuelTrend a={a} b={b} aName="Alpha" bName="Beta" now={NOW} />);
    expect(container.querySelectorAll('.compare-duel-trend__gap--a').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.compare-duel-trend__gap--b')).toHaveLength(0);
  });
});
