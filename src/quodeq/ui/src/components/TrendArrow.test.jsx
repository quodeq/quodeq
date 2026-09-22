import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import TrendArrow from './TrendArrow.jsx';

describe('TrendArrow — invalid delta guard', () => {
  it('does not show "NaN" for a non-numeric delta, falling back to the trend copy', () => {
    render(<TrendArrow trend="stable" delta="not-a-number" />);
    const el = screen.getByRole('img');
    expect(el).toHaveAttribute('title', 'stable');
    expect(el).toHaveAttribute('aria-label', 'stable');
    expect(el.getAttribute('title')).not.toMatch(/NaN/);
  });

  it('still renders the signed delta for a valid numeric delta', () => {
    render(<TrendArrow trend="up" delta={1.25} />);
    const el = screen.getByRole('img');
    expect(el).toHaveAttribute('title', '+1.25');
  });

  it('falls back to empty title when both delta and trend are absent', () => {
    render(<TrendArrow trend={undefined} delta={undefined} />);
    const el = screen.getByRole('img');
    expect(el).toHaveAttribute('title', '');
  });
});
