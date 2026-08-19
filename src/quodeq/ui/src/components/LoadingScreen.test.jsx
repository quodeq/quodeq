import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import LoadingScreen from './LoadingScreen.jsx';

describe('LoadingScreen tips', () => {
  it('shows no tip without the tips prop', () => {
    const { container } = render(<LoadingScreen />);
    expect(container.querySelector('.loading-tip')).toBeNull();
  });

  it('shows a tip only after the delay, then rotates to a different one', async () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<LoadingScreen tips />);
      expect(container.querySelector('.loading-tip')).toBeNull();
      await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
      const first = container.querySelector('.loading-tip');
      expect(first).toBeTruthy();
      const firstText = first.textContent;
      await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
      expect(container.querySelector('.loading-tip').textContent).not.toBe(firstText);
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders the warm-up notice when a snapshot is active', () => {
    const { container } = render(
      <LoadingScreen warmup={{ active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'x' }} />,
    );
    expect(container.querySelector('.warmup-notice')).toBeTruthy();
  });
});
