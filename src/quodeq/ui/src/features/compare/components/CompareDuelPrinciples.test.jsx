import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import CompareDuelPrinciples from './CompareDuelPrinciples.jsx';

const principles = [
  { key: 'security', label: 'Security', items: [{ key: 'integrity', label: 'Integrity', a: 7, b: 5.5, gap: 1.5 }] },
  { key: 'usability', label: 'Usability', items: [{ key: 'clarity', label: 'Clarity', a: 6, b: 6, gap: 0 }] },
];

describe('CompareDuelPrinciples', () => {
  it('repeats the matching dimension scores in a group heading, none when that dimension is absent', () => {
    const dimensions = [{ key: 'security', label: 'Security', a: 7, b: 5.5, gap: 1.5, shared: true }];
    const { container } = render(<CompareDuelPrinciples principles={principles} dimensions={dimensions} />);
    const groups = container.querySelectorAll('.compare-duel-principles__group');
    expect(groups).toHaveLength(2);
    const [sec, use] = groups;
    expect(sec.querySelector('.compare-duel-principles__dimScores').textContent).toBe('7.05.5+1.5');
    expect(use.querySelector('.compare-duel-principles__dimScores')).toBeNull();
    expect(container.querySelectorAll('.compare-duel-principles__row')).toHaveLength(2);
  });

  it('falls back to the no-shared message without groups', () => {
    const { container } = render(<CompareDuelPrinciples principles={[]} dimensions={[]} />);
    expect(container.querySelector('.compare-duel-principles')).toBeNull();
    expect(container.querySelector('.compare-panel__fallback')).not.toBeNull();
  });
});
