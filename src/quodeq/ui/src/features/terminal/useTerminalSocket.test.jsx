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
}
beforeEach(() => { MockWS.instances = []; globalThis.WebSocket = MockWS; });
afterEach(() => vi.restoreAllMocks());

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
