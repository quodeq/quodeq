import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTerminalSocket } from './useTerminalSocket.js';

class MockWS {
  static instances = [];
  constructor(url) { this.url = url; this.sent = []; this.readyState = 0; MockWS.instances.push(this);
    this.onopen = null; this.onmessage = null; this.onclose = null; }
  send(d) { this.sent.push(d); }
  close() { this.readyState = 3; this.onclose && this.onclose(); }
  _open() { this.readyState = 1; this.onopen && this.onopen(); }
  _msg(data) { this.onmessage && this.onmessage({ data }); }
  _drop(code) { this.readyState = 3; this.onclose && this.onclose({ code }); }
}
beforeEach(() => { MockWS.instances = []; globalThis.WebSocket = MockWS; });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

it('reconnects (new socket) when restartKey changes', () => {
  const { rerender } = renderHook(
    ({ rk }) => useTerminalSocket({ active: true, onData: () => {}, restartKey: rk }),
    { initialProps: { rk: 0 } },
  );
  expect(MockWS.instances.length).toBe(1);
  const first = MockWS.instances[0];
  act(() => rerender({ rk: 1 }));
  expect(first.readyState).toBe(3);           // old socket torn down (CLOSED)
  expect(MockWS.instances.length).toBe(2);    // fresh socket opened
});

it('connects when active, forwards data, sends tagged frames', () => {
  const got = [];
  const { result } = renderHook(() => useTerminalSocket({ active: true, onData: (s) => got.push(s) }));
  const ws = MockWS.instances[0];
  act(() => ws._open());
  expect(result.current.status).toBe('open');
  act(() => ws._msg('0hello'));
  expect(got).toEqual(['hello']);
  act(() => result.current.send('ls\n'));
  expect(ws.sent).toContain('0ls\n');
  act(() => result.current.resize(100, 40));
  expect(ws.sent.some((m) => m.startsWith('1') && m.includes('"cols":100'))).toBe(true);
});

it('does not connect when inactive', () => {
  renderHook(() => useTerminalSocket({ active: false, onData: () => {} }));
  expect(MockWS.instances.length).toBe(0);
});

it('fires onOpen on EVERY socket open so the pane can reset before scrollback replay', () => {
  // The server replays scrollback on every connect; without a reset the
  // client appends it under the existing buffer and the whole session
  // prints twice on a live-backend reconnect (sleep/wake). onOpen lets the
  // pane term.reset() first, on the initial open AND every reconnect.
  const opens = [];
  const { result } = renderHook(() => useTerminalSocket({
    active: true, onData: () => {}, onOpen: () => opens.push('open'),
  }));
  act(() => MockWS.instances[0]._open());
  expect(opens).toEqual(['open']);
  act(() => MockWS.instances[0]._drop(1006));
  act(() => result.current.reconnectNow());
  act(() => MockWS.instances[1]._open());
  expect(opens).toEqual(['open', 'open']);
});

it('auto-reconnects after an unexpected close, with growing backoff', () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useTerminalSocket({ active: true, onData: () => {} }));
  act(() => MockWS.instances[0]._open());
  // Server dies (e.g. restart): abnormal close, no app close code.
  act(() => MockWS.instances[0]._drop(1006));
  expect(result.current.status).toBe('reconnecting');
  expect(MockWS.instances.length).toBe(1);      // waits out the backoff first
  act(() => vi.advanceTimersByTime(500));
  expect(MockWS.instances.length).toBe(2);      // first retry after 500ms
  // Retry fails too (server still down): next delay doubles to 1000ms.
  act(() => MockWS.instances[1]._drop(1006));
  act(() => vi.advanceTimersByTime(500));
  expect(MockWS.instances.length).toBe(2);      // not yet
  act(() => vi.advanceTimersByTime(500));
  expect(MockWS.instances.length).toBe(3);      // second retry after 1000ms
  // Server is back: a successful open resets the backoff and the status.
  act(() => MockWS.instances[2]._open());
  expect(result.current.status).toBe('open');
});

it('reports busy and does not retry when another window owns the terminal', () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useTerminalSocket({ active: true, onData: () => {} }));
  act(() => MockWS.instances[0]._drop(4002));   // server: single-connection lock held
  expect(result.current.status).toBe('busy');
  act(() => vi.advanceTimersByTime(60000));
  expect(MockWS.instances.length).toBe(1);      // no auto-retry ping-pong
});

it('reports refused and does not retry when the gate rejects the connection', () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useTerminalSocket({ active: true, onData: () => {} }));
  act(() => MockWS.instances[0]._drop(4003));
  expect(result.current.status).toBe('refused');
  act(() => vi.advanceTimersByTime(60000));
  expect(MockWS.instances.length).toBe(1);
});

it('reconnectNow retries immediately, skipping the pending backoff', () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useTerminalSocket({ active: true, onData: () => {} }));
  act(() => MockWS.instances[0]._open());
  act(() => MockWS.instances[0]._drop(1006));
  expect(MockWS.instances.length).toBe(1);
  act(() => result.current.reconnectNow());
  expect(MockWS.instances.length).toBe(2);      // immediate, no timer wait
});

it('unmount during a pending retry cancels the timer (no zombie sockets)', () => {
  vi.useFakeTimers();
  const { unmount } = renderHook(() => useTerminalSocket({ active: true, onData: () => {} }));
  act(() => MockWS.instances[0]._open());
  act(() => MockWS.instances[0]._drop(1006));
  unmount();
  act(() => vi.advanceTimersByTime(60000));
  expect(MockWS.instances.length).toBe(1);
});
