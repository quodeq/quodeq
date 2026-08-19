import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import WarmupNotice from './WarmupNotice.jsx';

describe('WarmupNotice', () => {
  it('renders nothing when warm-up is inactive or absent', () => {
    expect(render(<WarmupNotice warmup={null} />).container.firstChild).toBeNull();
    expect(render(<WarmupNotice warmup={{ active: false, projectsDone: 2, projectsTotal: 2 }} />).container.firstChild).toBeNull();
  });

  it('shows determinate progress with the current project name', () => {
    const { container, getByText } = render(
      <WarmupNotice warmup={{ active: true, projectsDone: 1, projectsTotal: 6, currentProjectName: 'my-app' }} />,
    );
    expect(getByText(/Project 2 of 6: my-app/)).toBeInTheDocument();
    expect(container.querySelector('.warmup-notice__fill').style.width).toBe('17%');
  });

  it('falls back to the unnamed label when no current project name', () => {
    const { getByText } = render(
      <WarmupNotice warmup={{ active: true, projectsDone: 0, projectsTotal: 3, currentProjectName: null }} />,
    );
    expect(getByText(/Project 1 of 3$/)).toBeInTheDocument();
  });

  it('holds a full bar briefly when the warm-up completes, then hides', async () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(
        <WarmupNotice warmup={{ active: true, projectsDone: 5, projectsTotal: 6, currentProjectName: 'last-one' }} />,
      );
      rerender(<WarmupNotice warmup={{ active: false, projectsDone: 6, projectsTotal: 6, currentProjectName: null }} />);
      // The bar finishes full instead of vanishing from 83% straight to gone.
      expect(container.querySelector('.warmup-notice__fill').style.width).toBe('100%');
      expect(container.textContent).toContain('Scores refreshed');
      await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
      expect(container.querySelector('.warmup-notice')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not linger when it was never active', async () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<WarmupNotice warmup={null} />);
      rerender(<WarmupNotice warmup={{ active: false, projectsDone: 2, projectsTotal: 2 }} />);
      expect(container.querySelector('.warmup-notice')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
