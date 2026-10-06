import { describe, it, expect, vi, beforeEach } from 'vitest';
import { disconnectShared, SHARED_DISCONNECT_TIMEOUT_MS } from './sharedStatus.js';
import { request } from './request.js';

vi.mock('./request.js', () => ({ request: vi.fn() }));

// A disconnect waits server-side for the shared warm-up to finish the project
// in flight before it removes the clone, which can outlast the default 30 s
// request timeout on a large project. The UI must not report a failure for a
// disconnect that then succeeds a few seconds later.
describe('disconnectShared', () => {
  beforeEach(() => { request.mockReset(); request.mockResolvedValue({ configured: false }); });

  it('allows the server time to finish the project the warm-up is on', async () => {
    await disconnectShared();
    expect(SHARED_DISCONNECT_TIMEOUT_MS).toBe(120000);
    expect(request).toHaveBeenCalledWith('/shared/config?confirm=true', {
      method: 'DELETE', timeout: SHARED_DISCONNECT_TIMEOUT_MS,
    });
  });
});
