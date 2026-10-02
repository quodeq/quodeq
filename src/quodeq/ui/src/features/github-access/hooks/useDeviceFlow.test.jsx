import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useDeviceFlow } from './useDeviceFlow.js';

const code = { userCode: 'ABCD-1234', verificationUri: 'https://github.com/login/device', expiresIn: 900, interval: 5 };

describe('useDeviceFlow', () => {
  it('begins, shows the code, polls to done and reports the login', async () => {
    const statuses = [
      { state: 'awaiting_user', login: null, error: null },
      { state: 'done', login: 'victor', error: null },
    ];
    const getDeviceFlow = vi.fn(async () => statuses.shift());
    const onSignedIn = vi.fn();
    const { result } = renderHook(() => useDeviceFlow({
      startDeviceFlow: vi.fn(async () => code), getDeviceFlow, onSignedIn, pollMs: 5,
    }));
    expect(result.current.phase).toBe('idle');
    await act(async () => { await result.current.begin(); });
    expect(result.current.userCode).toBe('ABCD-1234');
    expect(result.current.verificationUri).toBe(code.verificationUri);
    await waitFor(() => expect(result.current.phase).toBe('done'));
    expect(result.current.login).toBe('victor');
    expect(onSignedIn).toHaveBeenCalledWith('victor');
    const callsAfterDone = getDeviceFlow.mock.calls.length;
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(getDeviceFlow.mock.calls.length).toBe(callsAfterDone); // polling stopped
  });

  it('expired and denied are terminal and reset returns to idle', async () => {
    const getDeviceFlow = vi.fn(async () => ({ state: 'expired', login: null, error: null }));
    const { result } = renderHook(() => useDeviceFlow({
      startDeviceFlow: vi.fn(async () => code), getDeviceFlow, onSignedIn: vi.fn(), pollMs: 5,
    }));
    await act(async () => { await result.current.begin(); });
    await waitFor(() => expect(result.current.phase).toBe('expired'));
    act(() => result.current.reset());
    expect(result.current.phase).toBe('idle');
    expect(result.current.userCode).toBeNull();
  });

  it('a failed start surfaces the mapped error', async () => {
    const err = Object.assign(new Error('offline'), { code: 'OFFLINE', status: 503, body: {} });
    const { result } = renderHook(() => useDeviceFlow({
      startDeviceFlow: vi.fn(async () => { throw err; }), getDeviceFlow: vi.fn(), onSignedIn: vi.fn(),
    }));
    await act(async () => { await result.current.begin(); });
    expect(result.current.phase).toBe('error');
    expect(result.current.error).toMatch(/GitHub couldn't be reached/);
  });
});
