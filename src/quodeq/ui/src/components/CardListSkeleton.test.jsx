import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CardListSkeleton from './CardListSkeleton.jsx';

// DeferredMount's fallback used to be an absolutely-positioned inline
// spinner that reserved zero height: the page jumped from shell-only to
// full list height when the VirtualList mounted. This skeleton stands in
// for the card list itself, so the fallback commit already has a list-like
// footprint below the header and pills.
describe('CardListSkeleton', () => {
  it('renders a section-header bar and 4 card bars by default', () => {
    const { container } = render(<CardListSkeleton />);
    expect(container.querySelectorAll('.card-list-skeleton__bar--header').length).toBe(1);
    expect(container.querySelectorAll('.card-list-skeleton__bar--card').length).toBe(4);
  });

  it('honors a custom row count', () => {
    const { container } = render(<CardListSkeleton rows={2} />);
    expect(container.querySelectorAll('.card-list-skeleton__bar--card').length).toBe(2);
  });

  it('is quiet: aria-busy container, aria-hidden visuals, no spinner', () => {
    const { container } = render(<CardListSkeleton />);
    const root = container.querySelector('.card-list-skeleton');
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(root).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.loading-screen')).toBeFalsy();
  });
});
