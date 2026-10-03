import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CompareDeltaBadge from './CompareDeltaBadge.jsx';

describe('CompareDeltaBadge', () => {
  it('shows the current delta as a plain badge', () => {
    const { container } = render(<CompareDeltaBadge delta={0.4} lastDelta={-1} />);
    expect(container.querySelector('.compare-delta--old')).toBeNull();
    expect(container.firstChild).not.toBeNull();
  });

  it('falls back to the last known delta, marked as old', () => {
    const { container } = render(<CompareDeltaBadge delta={null} lastDelta={-0.3} />);
    const old = container.querySelector('.compare-delta--old');
    expect(old).not.toBeNull();
    expect(old).toHaveAttribute('title');
    expect(old.firstChild).not.toBeNull();
  });

  it('renders nothing without either delta', () => {
    const { container } = render(<CompareDeltaBadge delta={null} lastDelta={undefined} />);
    expect(container.innerHTML).toBe('');
  });
});
