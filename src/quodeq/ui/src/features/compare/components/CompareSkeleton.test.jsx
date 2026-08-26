import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CompareSkeleton from './CompareSkeleton.jsx';

// Pre-projectsLoaded stand-in for the fleet table. Once projects load, the
// page renders immediately and rows fill in progressively (per-row pending
// marks), so this only covers the initial wait.
describe('CompareSkeleton', () => {
  it('renders a header bar and 5 fleet-row bars', () => {
    const { container } = render(<CompareSkeleton />);
    expect(container.querySelectorAll('.compare-skeleton__bar--header').length).toBe(1);
    expect(container.querySelectorAll('.compare-skeleton__bar--row').length).toBe(5);
  });

  it('is quiet: aria-busy container, aria-hidden, no spinner', () => {
    const { container } = render(<CompareSkeleton />);
    const root = container.querySelector('.compare-skeleton');
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(root).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.loading-screen')).toBeFalsy();
  });
});
