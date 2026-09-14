import { describe, it, expect } from 'vitest';
import { copyToClipboard } from './clipboard.js';

describe('copyToClipboard', () => {
  it('resolves false without throwing when clipboard is unavailable', async () => {
    const orig = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    await expect(copyToClipboard('x')).resolves.toBe(false);
    Object.defineProperty(navigator, 'clipboard', { value: orig, configurable: true });
  });

  it('resolves true when the write succeeds', async () => {
    const orig = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: () => Promise.resolve() },
      configurable: true,
    });
    await expect(copyToClipboard('x')).resolves.toBe(true);
    Object.defineProperty(navigator, 'clipboard', { value: orig, configurable: true });
  });

  it('resolves false (never rejects) when the write fails', async () => {
    const orig = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: () => Promise.reject(new Error('denied')) },
      configurable: true,
    });
    await expect(copyToClipboard('x')).resolves.toBe(false);
    Object.defineProperty(navigator, 'clipboard', { value: orig, configurable: true });
  });
});
