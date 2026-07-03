import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAssistantStream } from './useAssistantStream.js';

class MockES {
  static instances = [];
  constructor(url) { this.url = url; this._h = {}; this.readyState = 0; MockES.instances.push(this); }
  addEventListener(n, f) { (this._h[n] = this._h[n] || []).push(f); }
  set onmessage(f) { this._m = f; } get onmessage() { return this._m; }
  set onerror(f) { this._e = f; } get onerror() { return this._e; }
  emit(n, data) { const ev = { data: JSON.stringify(data) };
    if (n === 'message' && this._m) this._m(ev); (this._h[n] || []).forEach((f) => f(ev)); }
  close() { this.readyState = 2; this.closed = true; }
}

beforeEach(() => { vi.useFakeTimers(); MockES.instances = []; globalThis.EventSource = MockES; });
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function flush() { act(() => { vi.advanceTimersByTime(200); }); }

it('accumulates tokens into one assistant message', () => {
  const { result } = renderHook(() => useAssistantStream('s1'));
  const es = MockES.instances[0];
  act(() => { es.emit('message', { type: 'token', text: 'Hel' }); es.emit('message', { type: 'token', text: 'lo' }); });
  flush();
  const assistant = result.current.messages.find((m) => m.role === 'assistant');
  expect(assistant.text).toBe('Hello');
  expect(result.current.streaming).toBe(true);
});

it('records tool_call and action_draft frames', () => {
  const { result } = renderHook(() => useAssistantStream('s1'));
  const es = MockES.instances[0];
  act(() => {
    es.emit('message', { type: 'tool_call', name: 'get_scores' });
    es.emit('message', { type: 'action_draft', actionId: 'a1', actionType: 'create_standard',
      summary: { id: 'x', name: 'X', principleCount: 2 } });
  });
  flush();
  expect(result.current.messages.some((m) => m.role === 'tool' && m.name === 'get_scores')).toBe(true);
  expect(result.current.messages.some((m) => m.role === 'action' && m.actionId === 'a1')).toBe(true);
});

it('done ends streaming and calls onDone', () => {
  const onDone = vi.fn();
  const { result } = renderHook(() => useAssistantStream('s1', { onDone }));
  const es = MockES.instances[0];
  act(() => { es.emit('done', { type: 'done' }); });
  expect(result.current.streaming).toBe(false);
  expect(onDone).toHaveBeenCalledTimes(1);
  expect(es.closed).toBe(true);
});

it('error frame surfaces error and stops streaming', () => {
  const { result } = renderHook(() => useAssistantStream('s1'));
  const es = MockES.instances[0];
  act(() => { es.emit('message', { type: 'error', message: 'boom' }); });
  expect(result.current.error).toBe('boom');
  expect(result.current.streaming).toBe(false);
});

it('null sessionId opens no stream', () => {
  renderHook(() => useAssistantStream(null));
  expect(MockES.instances.length).toBe(0);
});
