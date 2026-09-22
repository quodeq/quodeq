import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import CompareDuelTrend from './CompareDuelTrend.jsx';

describe('CompareDuelTrend — empty combined series', () => {
  it('renders nothing instead of an Infinity/NaN-poisoned chart when both series are empty', () => {
    const { container } = render(<CompareDuelTrend a={[]} b={[]} aName="Alpha" bName="Beta" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing instead of a NaN-poisoned chart when a dateISO is unparseable', () => {
    const a = [{ dateISO: 'not-a-date', value: 7 }, { dateISO: '2026-02-01T00:00:00.000Z', value: 7.5 }];
    const b = [{ dateISO: '2026-01-15T00:00:00.000Z', value: 6 }];
    const { container } = render(<CompareDuelTrend a={a} b={b} aName="Alpha" bName="Beta" />);
    expect(container).toBeEmptyDOMElement();
  });
});
