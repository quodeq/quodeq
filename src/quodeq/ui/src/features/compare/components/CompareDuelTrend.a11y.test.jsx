import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDuelTrend from './CompareDuelTrend.jsx';

const seriesA = [
  { dateISO: '2026-08-01T00:00:00.000Z', value: 6.2 },
  { dateISO: '2026-09-01T00:00:00.000Z', value: 7.1 },
];
const seriesB = [
  { dateISO: '2026-08-10T00:00:00.000Z', value: 5.4 },
  { dateISO: '2026-09-05T00:00:00.000Z', value: 5.9 },
];

describe('CompareDuelTrend accessibility (#6316)', () => {
  it('names the chart image after both projects it plots', () => {
    render(<CompareDuelTrend a={seriesA} b={seriesB} aName="Alpha" bName="Beta" />);
    const chart = screen.getByRole('img', { name: /Score trend/ });
    expect(chart).toHaveAttribute('aria-label', 'Score trend of Alpha and Beta over time');
  });

  it('exposes exactly one named image for the plot', () => {
    render(<CompareDuelTrend a={seriesA} b={seriesB} aName="Alpha" bName="Beta" />);
    expect(screen.getAllByRole('img')).toHaveLength(1);
  });
});
