import { describe, it, expect, vi } from 'vitest';
import { copyToClipboard } from './clipboard.js';

describe('copyToClipboard', () => {
  it('resolves false without throwing when clipboard is unavailable', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined });
    await expect(copyToClipboard('x')).resolves.toBe(false);

  });

  it('resolves true when the write succeeds', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: () => Promise.resolve() } });
    await expect(copyToClipboard('x')).resolves.toBe(true);

  });

  it('resolves false (never rejects) when the write fails', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: () => Promise.reject(new Error('denied')) } });
    await expect(copyToClipboard('x')).resolves.toBe(false);

  });
});
