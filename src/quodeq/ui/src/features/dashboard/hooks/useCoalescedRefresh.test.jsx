import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCoalescedRefresh } from './useCoalescedRefresh.js';

// A promise the test controls the settlement of, so assertions can run
// while a call is genuinely still in flight.
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// Races a promise against a timer so a regression to the permanent-hang bug
// fails this test (timeout) instead of hanging the whole vitest run.
function withTimeout(promise, ms = 2000) {
  return Promise.race([
    promise.then(() => 'resolved', () => 'rejected'),
    new Promise((_, reject) => setTimeout(() => reject(new Error('timed out -- promise never settled')), ms)),
  ]);
}

describe('useCoalescedRefresh', () => {
  it('resolves on a plain successful call', async () => {
    const refreshCore = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useCoalescedRefresh(refreshCore));

    let p;
    act(() => { p = result.current.refresh(); });
    await expect(withTimeout(p)).resolves.toBe('resolved');
    expect(refreshCore).toHaveBeenCalledTimes(1);
  });

  // The reported permanent hang: the FIRST refreshCore() call (the one
  // outside the while-loop) rejects while a second caller is already queued
  // in waitersRef. Before the fix, control jumped straight from that await
  // to `finally`, so the queued waiter's promise was never resolved OR
  // rejected -- it hung forever. Both the initiator's and the queued
  // caller's promises must now settle (reject) with the failure.
  it('rejects a queued waiter instead of hanging when the leading refreshCore() call fails', async () => {
    const d = deferred();
    const refreshCore = vi.fn(() => d.promise);
    const { result } = renderHook(() => useCoalescedRefresh(refreshCore));

    let p1;
    let p2;
    act(() => {
      p1 = result.current.refresh(); // starts the in-flight round
      p2 = result.current.refresh(); // queued while the first is running
    });
    expect(refreshCore).toHaveBeenCalledTimes(1);

    const failure = new Error('refresh failed');
    let outcome1;
    let outcome2;
    await act(async () => {
      d.reject(failure);
      outcome1 = await withTimeout(p1);
      outcome2 = await withTimeout(p2);
    });

    expect(outcome1).toBe('rejected');
    expect(outcome2).toBe('rejected');
    await expect(p1).rejects.toBe(failure);
    await expect(p2).rejects.toBe(failure);
    // The failed round never entered the while-loop's retry path -- a
    // second refreshCore() call must not have been made.
    expect(refreshCore).toHaveBeenCalledTimes(1);
    expect(result.current.refreshing).toBe(false);
  });

  it('rejects queued waiters when the coalesced retry round (inside the while-loop) fails', async () => {
    const first = deferred();
    const second = deferred();
    const refreshCore = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const { result } = renderHook(() => useCoalescedRefresh(refreshCore));

    let p1;
    let p2;
    act(() => {
      p1 = result.current.refresh();
      p2 = result.current.refresh(); // queued -> satisfied by the retry round
    });

    const failure = new Error('retry round failed');
    await act(async () => {
      first.resolve(undefined); // leading round succeeds, enters while-loop
      await Promise.resolve(); // let the retry round's refreshCore() start
      second.reject(failure);
      await withTimeout(p1);
      await withTimeout(p2);
    });

    await expect(p1).rejects.toBe(failure);
    await expect(p2).rejects.toBe(failure);
    expect(refreshCore).toHaveBeenCalledTimes(2);
  });
});
