// src/quodeq/ui/src/api/assistant.test.jsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as assistant from './assistant.js';

let calls;
beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (url, opts) => {
    calls.push({ url, opts });
    return { ok: true, json: async () => ({ sessionId: 's1', accepted: true, status: 'rejected' }) };
  });
});
afterEach(() => { vi.restoreAllMocks(); });

it('createAssistantSession POSTs the payload', async () => {
  await assistant.createAssistantSession({ provider: 'claude', model: 'sonnet' });
  expect(calls[0].url).toBe('/api/assistant/sessions');
  expect(calls[0].opts.method).toBe('POST');
  expect(JSON.parse(calls[0].opts.body)).toEqual({ provider: 'claude', model: 'sonnet' });
});

it('postAssistantMessage targets the session', async () => {
  await assistant.postAssistantMessage('s 1', { text: 'hi' });
  expect(calls[0].url).toBe('/api/assistant/sessions/s%201/messages');
  expect(JSON.parse(calls[0].opts.body)).toEqual({ text: 'hi' });
});

it('apply/reject target the action', async () => {
  await assistant.applyAssistantAction('a1');
  await assistant.rejectAssistantAction('a1');
  expect(calls[0].url).toBe('/api/assistant/actions/a1/apply');
  expect(calls[1].url).toBe('/api/assistant/actions/a1/reject');
});

it('assistantEventsUrl builds an encoded SSE url with after', () => {
  expect(assistant.assistantEventsUrl('s 1', 7)).toBe('/api/assistant/sessions/s%201/events?after=7');
});
