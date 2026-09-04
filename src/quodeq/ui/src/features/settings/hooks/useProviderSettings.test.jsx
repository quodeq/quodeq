import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useProviderSettings, { saveProviderSetting } from './useProviderSettings.js';

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
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
      result.current.update('api-key', 'secret');
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
