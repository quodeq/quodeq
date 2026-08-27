import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ViolationsSkeleton from './ViolationsSkeleton.jsx';

// Footprint stand-in for the loaded violations page: the flag-pill row and
// the by-dimension groups. Replaces the floating inline spinner so data
// arrival swaps content in place instead of growing the page.
describe('ViolationsSkeleton', () => {
  it('renders the flag-pill row with 3 pill placeholders', () => {
    const { container } = render(<ViolationsSkeleton />);
    const row = container.querySelector('.violations-flag-row');
    expect(row).toBeTruthy();
    expect(row.querySelectorAll('.violations-skeleton__pill').length).toBe(3);
  });

  it('renders dimension group placeholders, each with a header and card bars', () => {
    const { container } = render(<ViolationsSkeleton />);
    const groups = container.querySelectorAll('.violations-skeleton__group');
    expect(groups.length).toBe(3);
    groups.forEach((group) => {
      expect(group.querySelector('.violations-skeleton__bar--group-header')).toBeTruthy();
      expect(group.querySelectorAll('.violations-skeleton__bar--card').length).toBe(2);
    });
  });

  it('is quiet: aria-busy container, aria-hidden, no spinner', () => {
    const { container } = render(<ViolationsSkeleton />);
    const root = container.querySelector('.violations-skeleton');
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(root).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.loading-screen')).toBeFalsy();
  });
});
