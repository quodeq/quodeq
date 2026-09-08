import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import useProviderSettings, { saveProviderSetting, saveProviderApiKey, API_KEY_CONFIGURED_SENTINEL } from './useProviderSettings.js';
import { saveProviderKey } from '../../../api/providers.js';

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));

vi.mock('../../../api/providers.js', () => ({
  saveProviderKey: vi.fn(),
}));

describe('useProviderSettings', () => {
  let mockStorage;

  beforeEach(() => {
    mockStorage = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    showToast.mockClear();
    saveProviderKey.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads default state when storage returns null', () => {
    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );
    expect(result.current.state.model).toBe('');
    expect(result.current.state.subagents).toBe('1');
  });

  it('update sets state immediately', () => {
    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );
    act(() => {
      result.current.update('model', 'llama3');
    });
    expect(result.current.state.model).toBe('llama3');
  });

  it('update calls storage.setItem', () => {
    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );
    act(() => {
      result.current.update('model', 'llama3');
    });
    expect(mockStorage.setItem).toHaveBeenCalled();
  });

  it('update does not throw when storage.setItem throws (quota/SecurityError)', () => {
    // Finding #324: setItem throwing must not crash the hook.
    mockStorage.setItem.mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );

    // This must not throw.
    expect(() => {
      act(() => {
        result.current.update('model', 'llama3');
      });
    }).not.toThrow();

    // State was still updated in memory even though storage failed.
    expect(result.current.state.model).toBe('llama3');
  });

  it('update swallows storage error and warns via console.warn', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockStorage.setItem.mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('model', 'llama3');
    });

    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it('storage failure is surfaced via onPersistError, not only console.warn', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const storage = { setItem: () => { throw new DOMException('quota exceeded'); } };
    const onPersistError = vi.fn();

    saveProviderSetting('claude', 'model', 'sonnet', storage, { onPersistError });

    expect(onPersistError).toHaveBeenCalledWith(expect.any(DOMException));
  });

  it('update shows a toast (not just console.warn) when persistence fails', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockStorage.setItem.mockImplementation(() => {
      throw new DOMException('QuotaExceededError');
    });

    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('model', 'llama3');
    });

    expect(showToast).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(expect.any(String));
  });

  it('update does not show a toast when persistence succeeds', () => {
    const { result } = renderHook(() =>
      useProviderSettings('ollama', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('model', 'llama3');
    });

    expect(showToast).not.toHaveBeenCalled();
  });
});

describe('useProviderSettings api-key handling', () => {
  let mockStorage;

  beforeEach(() => {
    mockStorage = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    showToast.mockClear();
    saveProviderKey.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('update("api-key", value) calls the backend endpoint instead of storage.setItem with the raw value', async () => {
    saveProviderKey.mockResolvedValue({ stored: true, secure: true });
    const { result } = renderHook(() =>
      useProviderSettings('openai', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('api-key', 'sk-super-secret');
    });

    expect(saveProviderKey).toHaveBeenCalledWith('openai', 'sk-super-secret');
    await waitFor(() => {
      expect(mockStorage.setItem).toHaveBeenCalled();
    });
    for (const call of mockStorage.setItem.mock.calls) {
      expect(call[1]).not.toBe('sk-super-secret');
    }
  });

  it('on success, stores the "configured" sentinel, never the raw key', async () => {
    saveProviderKey.mockResolvedValue({ stored: true, secure: true });
    const { result } = renderHook(() =>
      useProviderSettings('openai', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('api-key', 'sk-super-secret');
    });

    await waitFor(() => {
      expect(result.current.state['api-key']).toBe(API_KEY_CONFIGURED_SENTINEL);
    });
    expect(mockStorage.setItem).toHaveBeenCalledWith('cc-openai-api-key', API_KEY_CONFIGURED_SENTINEL);
  });

  it('on backend failure (stored: false), warns and shows a toast without writing to storage', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    saveProviderKey.mockResolvedValue({ stored: false, secure: false });
    const { result } = renderHook(() =>
      useProviderSettings('openai', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('api-key', 'sk-super-secret');
    });

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledTimes(1);
    });
    expect(warnSpy).toHaveBeenCalled();
    expect(mockStorage.setItem).not.toHaveBeenCalled();
  });

  it('on network/request failure, warns and shows a toast without writing to storage', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    saveProviderKey.mockRejectedValue(new Error('network error'));
    const { result } = renderHook(() =>
      useProviderSettings('openai', {}, { storage: mockStorage })
    );

    act(() => {
      result.current.update('api-key', 'sk-super-secret');
    });

    await waitFor(() => {
      expect(showToast).toHaveBeenCalledTimes(1);
    });
    expect(warnSpy).toHaveBeenCalled();
    expect(mockStorage.setItem).not.toHaveBeenCalled();
  });

  it('saveProviderApiKey resolves false and never writes storage when the backend reports stored:false', async () => {
    saveProviderKey.mockResolvedValue({ stored: false, secure: false });
    const onPersistError = vi.fn();

    const ok = await saveProviderApiKey('openai', 'sk-super-secret', mockStorage, { onPersistError });

    expect(ok).toBe(false);
    expect(onPersistError).toHaveBeenCalled();
    expect(mockStorage.setItem).not.toHaveBeenCalled();
  });
});

describe('useProviderSettings effective defaults', () => {
  it('unset per-dimension displays Grouped (the mode a run actually uses)', () => {
    const mockStorage = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };
    const { result } = renderHook(() =>
      useProviderSettings('claude', {}, { storage: mockStorage })
    );
    // The engine defaults to one grouped/consolidated pass; a highlighted
    // "Per-dimension" pill for an untouched toggle was a lie.
    expect(result.current.state['per-dimension']).toBe('false');
  });
});
