import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import RunOverviewSkeleton from './RunOverviewSkeleton.jsx';

describe('RunOverviewSkeleton', () => {
  it('shows the run date immediately while the payload loads', () => {
    render(<RunOverviewSkeleton dateLabel="Jul 4, 2026" />);
    expect(screen.getByText('Jul 4, 2026')).toBeTruthy();
  });

  it('mirrors the hero stat layout', () => {
    render(<RunOverviewSkeleton dateLabel="Jul 4, 2026" />);
    for (const label of ['SCORE', 'VIOLATIONS', 'COMPLIANCE', 'RATIO']) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it('is announced as a loading status', () => {
    render(<RunOverviewSkeleton />);
    expect(screen.getByRole('status', { name: /loading run details/i })).toBeTruthy();
  });

  it('renders placeholder blocks without a date label', () => {
    const { container } = render(<RunOverviewSkeleton />);
    expect(container.querySelectorAll('.run-skel__block').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('.run-skel__card').length).toBe(6);
  });
});
