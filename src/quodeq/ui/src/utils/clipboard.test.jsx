import { describe, it, expect } from 'vitest';
import { copyToClipboard } from './clipboard.js';

describe('copyToClipboard', () => {
  it('no-ops without throwing when clipboard is unavailable', async () => {
    const orig = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    await expect(copyToClipboard('x')).resolves.toBeUndefined();
    Object.defineProperty(navigator, 'clipboard', { value: orig, configurable: true });
  });
});
