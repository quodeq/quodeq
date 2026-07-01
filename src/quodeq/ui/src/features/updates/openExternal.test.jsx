import { describe, it, expect, vi, afterEach } from 'vitest';
import { openExternal } from './openExternal.js';

// The URL handed to openExternal originates from the remote update API
// (status.latest_url / status.download_url), so it crosses a trust boundary.
// A malicious or MITM'd response must not be able to smuggle a javascript:,
// data:, or file: URL into window.open / pywebview.open_browser.
describe('openExternal', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens https URLs', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('https://github.com/quodeq/quodeq/releases/tag/v1.5.0');
    expect(open).toHaveBeenCalledWith(
      'https://github.com/quodeq/quodeq/releases/tag/v1.5.0', '_blank', 'noopener',
    );
  });

  it('opens http URLs', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('http://example.com/download');
    expect(open).toHaveBeenCalled();
  });

  it('blocks javascript: URLs', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('javascript:alert(document.cookie)');
    expect(open).not.toHaveBeenCalled();
  });

  it('blocks file: URLs', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('file:///etc/passwd');
    expect(open).not.toHaveBeenCalled();
  });

  it('blocks data: URLs', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('data:text/html,<script>alert(1)</script>');
    expect(open).not.toHaveBeenCalled();
  });

  it('ignores empty or unparseable input', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    openExternal('');
    openExternal(null);
    openExternal('not a url');
    expect(open).not.toHaveBeenCalled();
  });
});
