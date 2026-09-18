import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import CompareDuelTrend from './CompareDuelTrend.jsx';

describe('CompareDuelTrend — empty combined series', () => {
  it('renders nothing instead of an Infinity/NaN-poisoned chart when both series are empty', () => {
    const { container } = render(<CompareDuelTrend a={[]} b={[]} aName="Alpha" bName="Beta" />);
    expect(container).toBeEmptyDOMElement();
  });
});
