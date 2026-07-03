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

it('done ends the turn (streaming false, onDone) but keeps the stream OPEN', () => {
  const onDone = vi.fn();
  const { result } = renderHook(() => useAssistantStream('s1', { onDone }));
  const es = MockES.instances[0];
  act(() => { es.emit('done', { type: 'done' }); });
  expect(result.current.streaming).toBe(false);
  expect(onDone).toHaveBeenCalledTimes(1);
  // The connection must NOT close on a turn's done — it serves the next turn.
  expect(es.closed).toBeFalsy();
});

it('two turns over ONE stream produce two separate assistant bubbles', () => {
  const onDone = vi.fn();
  const { result } = renderHook(() => useAssistantStream('s1', { onDone }));
  const es = MockES.instances[0];

  // Turn 1: token "A" then done.
  act(() => { es.emit('message', { type: 'token', text: 'A' }); });
  flush();
  act(() => { es.emit('done', { type: 'done' }); });
  let assistants = result.current.messages.filter((m) => m.role === 'assistant');
  expect(assistants.map((m) => m.text)).toEqual(['A']);
  expect(result.current.streaming).toBe(false);
  expect(onDone).toHaveBeenCalledTimes(1);
  expect(es.closed).toBeFalsy();

  // Turn 2 over the SAME stream: token "B" then done.
  act(() => { es.emit('message', { type: 'token', text: 'B' }); });
  expect(result.current.streaming).toBe(true); // streaming re-arms for turn 2
  flush();
  act(() => { es.emit('done', { type: 'done' }); });
  assistants = result.current.messages.filter((m) => m.role === 'assistant');
  // Two distinct bubbles — turn 2 must NOT concatenate onto turn 1 ("AB").
  expect(assistants.map((m) => m.text)).toEqual(['A', 'B']);
  expect(result.current.streaming).toBe(false);
  expect(onDone).toHaveBeenCalledTimes(2);
  // The stream was never closed between the two turns.
  expect(es.closed).toBeFalsy();
  expect(MockES.instances.length).toBe(1);
});

it('an error frame keeps the stream open so a next turn still streams', () => {
  const { result } = renderHook(() => useAssistantStream('s1'));
  const es = MockES.instances[0];
  act(() => { es.emit('message', { type: 'error', message: 'boom' }); });
  expect(result.current.error).toBe('boom');
  expect(result.current.streaming).toBe(false);
  expect(es.closed).toBeFalsy();

  // A subsequent turn's token is processed into a fresh bubble and clears the
  // stale error.
  act(() => { es.emit('message', { type: 'token', text: 'retry' }); });
  flush();
  const assistants = result.current.messages.filter((m) => m.role === 'assistant');
  expect(assistants.map((m) => m.text)).toEqual(['retry']);
  expect(result.current.error).toBe(null);
  expect(result.current.streaming).toBe(true);
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

it('60s with no data frames at all times out (no heartbeat to save it)', () => {
  const { result } = renderHook(() => useAssistantStream('s1'));
  act(() => { vi.advanceTimersByTime(61000); });
  expect(result.current.error).toBe('stream timed out');
  expect(result.current.streaming).toBe(false);
});

it('a heartbeat data frame resets inactivity so a slow model does not time out', () => {
  // Simulates a slow local model (e.g. a cold-loading ~26B ollama model)
  // that produces no token/tool_call frames for a long stretch. The backend
  // now emits a real {"type":"heartbeat"} DATA frame every ~5s, which fires
  // EventSource's onmessage and resets the client's inactivity timer -
  // unlike ":keepalive" SSE comments, which EventSource ignores entirely.
  const { result } = renderHook(() => useAssistantStream('s1'));
  const es = MockES.instances[0];

  // ~40s of silence, then a heartbeat arrives - well before the 60s limit.
  act(() => { vi.advanceTimersByTime(40000); });
  act(() => { es.emit('message', { type: 'heartbeat' }); });

  // Advance to ~90s total elapsed: without the heartbeat's reset at ~40s,
  // this would exceed the 60s inactivity window and time out.
  act(() => { vi.advanceTimersByTime(50000); });

  expect(result.current.error).not.toBe('stream timed out');
  expect(result.current.streaming).toBe(true);
  // Heartbeats are liveness-only: they must never show up as a message.
  expect(result.current.messages.some((m) => m.role === 'heartbeat')).toBe(false);
  expect(result.current.messages.length).toBe(0);
});
