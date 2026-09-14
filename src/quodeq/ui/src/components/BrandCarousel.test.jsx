import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import BrandCarousel from './BrandCarousel.jsx';

describe('BrandCarousel', () => {
  it('renders the wordmark and an initial phrase', () => {
    const { container } = render(<BrandCarousel />);
    expect(container.querySelector('.sa-wordmark').textContent).toBe('quodeq');
    const phrase = container.querySelector('.sa-phrase');
    expect(phrase).not.toBeNull();
    expect(phrase.textContent.length).toBeGreaterThan(0);
  });

  it('exposes chevron hit targets for keyboard/click navigation', () => {
    const { container } = render(<BrandCarousel />);
    expect(container.querySelector('.sa-hit--left')).not.toBeNull();
    expect(container.querySelector('.sa-hit--right')).not.toBeNull();
  });

  describe('unmount cleanup', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('does not setState or re-arm after unmount, even mid-transition', () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const { unmount } = render(<BrandCarousel />);

      // Let the outer auto-advance timer fire so the inner transition timer
      // (the one that used to leak) gets scheduled, then unmount before it fires.
      act(() => { vi.advanceTimersByTime(3500); }); // AUTO_ADVANCE_MS
      unmount();

      // Advance well past the inner transition timer and several more
      // would-be re-arm cycles. Pre-fix, the inner setTimeout would still
      // fire, call setState on the unmounted tree, and reschedule itself
      // forever.
      act(() => { vi.advanceTimersByTime(60000); });

      const unmountedStateWarning = errorSpy.mock.calls.some((args) =>
        String(args[0]).includes("Can't perform a React state update on an unmounted component")
      );
      expect(unmountedStateWarning).toBe(false);
      expect(vi.getTimerCount()).toBe(0);

      errorSpy.mockRestore();
    });
  });
});
