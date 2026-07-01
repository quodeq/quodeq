import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./request.js', () => ({ request: vi.fn(() => Promise.resolve({ ok: true })) }));
import { request } from './request.js';
import {
  getUpdateStatus,
  checkForUpdates,
  dismissUpdate,
  setUpdateAutoCheck,
  markUpdateDisclosed,
} from './index.js';

beforeEach(() => { request.mockClear(); });

describe('update api', () => {
  it('getUpdateStatus GETs /update/status', () => {
    getUpdateStatus();
    expect(request).toHaveBeenCalledWith('/update/status');
  });

  it('checkForUpdates POSTs /update/check', () => {
    checkForUpdates();
    expect(request).toHaveBeenCalledWith('/update/check', { method: 'POST' });
  });

  it('dismissUpdate POSTs the version', () => {
    dismissUpdate('1.5.0');
    expect(request).toHaveBeenCalledWith('/update/dismiss', {
      method: 'POST',
      body: JSON.stringify({ version: '1.5.0' }),
    });
  });

  it('setUpdateAutoCheck POSTs the flag', () => {
    setUpdateAutoCheck(false);
    expect(request).toHaveBeenCalledWith('/update/settings', {
      method: 'POST',
      body: JSON.stringify({ auto_check_enabled: false }),
    });
  });

  it('markUpdateDisclosed POSTs disclosed', () => {
    markUpdateDisclosed();
    expect(request).toHaveBeenCalledWith('/update/settings', {
      method: 'POST',
      body: JSON.stringify({ disclosed: true }),
    });
  });
});
