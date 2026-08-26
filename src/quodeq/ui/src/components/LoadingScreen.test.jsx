import { describe, it, expect, vi } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import LoadingScreen, { FadingLoadingScreen } from './LoadingScreen.jsx';

describe('LoadingScreen tips', () => {
  it('shows no tip without the tips prop', () => {
    const { container } = render(<LoadingScreen />);
    expect(container.querySelector('.loading-tip')).toBeNull();
  });

  it('shows a tip only after the 300ms delay, then rotates to a different one', async () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<LoadingScreen tips />);
      expect(container.querySelector('.loading-tip')).toBeNull();
      await act(async () => { await vi.advanceTimersByTimeAsync(250); });
      expect(container.querySelector('.loading-tip')).toBeNull();
      await act(async () => { await vi.advanceTimersByTimeAsync(50); });
      const first = container.querySelector('.loading-tip');
      expect(first).toBeTruthy();
      const firstText = first.textContent;
      await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
      expect(container.querySelector('.loading-tip').textContent).not.toBe(firstText);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shuffles the rotation per mount: fresh launches open with different tips', async () => {
    vi.useFakeTimers();
    try {
      const firstTips = new Set();
      for (let i = 0; i < 8; i++) {
        const { container, unmount } = render(<LoadingScreen tips />);
        await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
        firstTips.add(container.querySelector('.loading-tip').textContent);
        unmount();
      }
      // 8 independent shuffles of 10 tips all opening identically has odds
      // of 1e-7; a sequential rotation always opens with the same tip.
      expect(firstTips.size).toBeGreaterThan(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('walks every tip exactly once before repeating', async () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<LoadingScreen tips />);
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      const seen = [];
      for (let i = 0; i < 10; i++) {
        seen.push(container.querySelector('.loading-tip').textContent);
        await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
      }
      expect(new Set(seen).size).toBe(10);
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

  it('keeps the tip right under the logo and the warm-up notice in the last (bottom) slot', async () => {
    vi.useFakeTimers();
    try {
      const { container } = render(
        <LoadingScreen tips warmup={{ active: true, projectsDone: 0, projectsTotal: 2, currentProjectName: 'x' }} />,
      );
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      const children = Array.from(container.querySelector('.loading-screen').children);
      const tipIdx = children.findIndex((el) => el.classList.contains('loading-tip'));
      const noticeIdx = children.findIndex((el) => el.classList.contains('warmup-notice'));
      expect(tipIdx).toBeGreaterThan(-1);
      expect(noticeIdx).toBeGreaterThan(tipIdx);
    } finally {
      vi.useRealTimers();
    }
  });
});

// The loader must leave gracefully: when `show` flips false it stays mounted
// with the leaving class while the fade-out plays, then unmounts. Ripping it
// out of the DOM on the same frame the content appears reads as a "break".
describe('FadingLoadingScreen', () => {
  it('renders the loader while show is true, without the leaving class', () => {
    const { container } = render(<FadingLoadingScreen show />);
    const screen = container.querySelector('.loading-screen');
    expect(screen).toBeTruthy();
    expect(screen.classList.contains('loading-screen--leaving')).toBe(false);
  });

  it('renders nothing when mounted with show=false', () => {
    const { container } = render(<FadingLoadingScreen show={false} />);
    expect(container.querySelector('.loading-screen')).toBeNull();
  });

  it('fades out then unmounts when show flips false', async () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<FadingLoadingScreen show />);
      rerender(<FadingLoadingScreen show={false} />);
      const leaving = container.querySelector('.loading-screen');
      expect(leaving).toBeTruthy();
      expect(leaving.classList.contains('loading-screen--leaving')).toBe(true);
      await act(async () => { await vi.advanceTimersByTimeAsync(400); });
      expect(container.querySelector('.loading-screen')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancels the pending unmount when show flips back true mid-fade', async () => {
    vi.useFakeTimers();
    try {
      const { container, rerender } = render(<FadingLoadingScreen show />);
      rerender(<FadingLoadingScreen show={false} />);
      rerender(<FadingLoadingScreen show />);
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      const screen = container.querySelector('.loading-screen');
      expect(screen).toBeTruthy();
      expect(screen.classList.contains('loading-screen--leaving')).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
