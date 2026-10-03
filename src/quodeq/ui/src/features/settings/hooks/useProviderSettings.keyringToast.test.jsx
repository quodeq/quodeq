// With no OS keyring and no plaintext opt-in, POST /api/provider/key answers
// a coded KEYRING_UNAVAILABLE 409. The key-save toast must show that copy
// (what to export, how to opt in), not the generic "browser storage" one.
//
// Own file: useProviderSettings.test.jsx sits at the 300-line cap.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import useProviderSettings from './useProviderSettings.js';
import { saveProviderKey } from '../../../api/providers.js';
import { t } from '../../../strings/index.js';

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));

vi.mock('../../../api/providers.js', () => ({
  saveProviderKey: vi.fn(),
}));

const storage = () => ({ getItem: vi.fn(() => null), setItem: vi.fn(), removeItem: vi.fn() });

function codedError(code, body) {
  const err = new Error('backend sentence');
  err.status = 409;
  err.code = code;
  err.body = body;
  return err;
}

describe('useProviderSettings api-key save failure toast', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    showToast.mockReset();
    saveProviderKey.mockReset();
  });

  it('shows the keyring copy with the env var for KEYRING_UNAVAILABLE', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    saveProviderKey.mockRejectedValue(codedError('KEYRING_UNAVAILABLE', {
      code: 'KEYRING_UNAVAILABLE', envVar: 'ANTHROPIC_API_KEY',
    }));
    const { result } = renderHook(() => useProviderSettings('claude', {}, { storage: storage() }));

    act(() => { result.current.update('api-key', 'sk-gated'); });

    await waitFor(() => expect(showToast).toHaveBeenCalledTimes(1));
    const shown = showToast.mock.calls[0][0];
    expect(shown).toBe(t('apiError.keyringUnavailable', { envVar: 'ANTHROPIC_API_KEY' }));
    expect(shown).toContain('ANTHROPIC_API_KEY');
    expect(shown).toContain('QUODEQ_ALLOW_PLAINTEXT_KEY=1');
  });

  it('keeps the generic persist copy for an uncoded failure', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    saveProviderKey.mockResolvedValue({ stored: false, secure: false });
    const { result } = renderHook(() => useProviderSettings('claude', {}, { storage: storage() }));

    act(() => { result.current.update('api-key', 'sk-x'); });

    await waitFor(() => expect(showToast).toHaveBeenCalledWith(t('settings.persistError')));
  });
});
