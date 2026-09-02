import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AssistantDrawerProvider, useAssistantDrawer } from './AssistantDrawerProvider.jsx';

// Split from AssistantDrawerProvider.test.jsx: session lifecycle
// (start/send/reset/stop), error surfacing, and the create-race guards.
// The full mock header + Probe harness are duplicated here (vi.mock
// hoisting is file-scoped).

vi.mock('../../api/assistant.js', () => ({
  createAssistantSession: vi.fn(async (payload) => ({ sessionId: 's1', readOnly: payload?.source === 'shared' })),
  postAssistantMessage: vi.fn(async () => ({ accepted: true })),
  stopAssistantTurn: vi.fn(async () => ({ stopping: true })),
  fetchAssistantWorkspace: vi.fn(async () => ({ worktree: null })),
  applyAssistantAction: vi.fn(async () => ({ applied: true })),
  rejectAssistantAction: vi.fn(async () => ({ rejected: true })),
  assistantEventsUrl: (id, a) => `/api/assistant/sessions/${id}/events?after=${a}`,
  fetchAssistantCatalog: vi.fn(async () => ({ commands: [], skills: [], actions: [] })),
}));
const _streamHooks = { onDone: null };
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: (_sessionId, opts) => {
    _streamHooks.onDone = opts?.onDone || null;  // capture so tests can fire it
    return { messages: [], streaming: false, error: null, reset: vi.fn() };
  },
}));
import { createAssistantSession, postAssistantMessage, stopAssistantTurn, fetchAssistantCatalog } from '../../api/assistant.js';

function Probe() {
  const d = useAssistantDrawer();
  return (
    <div>
      <span data-testid="open">{String(d.isOpen)}</span>
      <span data-testid="streaming">{String(d.streaming)}</span>
      <span data-testid="provider">{String(d.provider)}</span>
      <span data-testid="model">{String(d.model)}</span>
      <span data-testid="error">{String(d.error)}</span>
      <span data-testid="web">{String(d.webEnabled)}</span>
      <span data-testid="catalog">{JSON.stringify(d.catalog)}</span>
      <span data-testid="messages">{JSON.stringify(d.messages)}</span>
      <span data-testid="panels">{JSON.stringify(d.openPanels)}</span>
      <span data-testid="active">{d.activeTab}</span>
      <span data-testid="readonly">{String(d.readOnly)}</span>
      <button onClick={d.toggleWebEnabled}>web</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' })}>start</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' })}>startA</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' })}>startB</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r', source: 'shared' })}>startShared</button>
      <button onClick={d.toggle}>toggle</button>
      <button onClick={() => d.openTab('assistant')}>openAssistant</button>
      <button onClick={() => d.openTab('terminal')}>openTerminal</button>
      <button onClick={() => d.closePanel('assistant')}>closeAssistantPanel</button>
      <button onClick={() => d.sendMessage('hi', { activeTab: 'overview' })}>send</button>
      <button onClick={d.stopTurn}>stop</button>
      <button onClick={d.resetConversation}>reset</button>
      <button onClick={() => d.addLocalExchange?.('/help', 'HELP TEXT')}>localExchange</button>
    </div>
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => localStorage.clear());

it('streaming reflects an in-flight turn, not the open session/connection', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  // Opening a session must NOT look like loading (regression: streaming was
  // true on SSE connect, so the drawer span forever with a disabled input).
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('streaming').textContent).toBe('false');
  // Sending a message starts a turn → loading.
  await act(async () => { screen.getByText('send').click(); });
  expect(screen.getByTestId('streaming').textContent).toBe('true');
  // The stream's terminal done/error frame ends the turn → not loading.
  act(() => { _streamHooks.onDone?.(); });
  expect(screen.getByTestId('streaming').textContent).toBe('false');
});

it('toggle flips visibility', () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  expect(screen.getByTestId('open').textContent).toBe('false');
  act(() => screen.getByText('toggle').click());
  expect(screen.getByTestId('open').textContent).toBe('true');
});

it('startSession creates a session; sendMessage posts to it', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  expect(createAssistantSession).toHaveBeenCalledWith({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' });
  await act(async () => { screen.getByText('send').click(); });
  expect(postAssistantMessage).toHaveBeenCalledWith('s1', { text: 'hi', uiState: { activeTab: 'overview' }, webEnabled: false, writeEnabled: false });
});

it('exposes the active session provider/model for the drawer header', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  expect(screen.getByTestId('provider').textContent).toBe('null');
  expect(screen.getByTestId('model').textContent).toBe('null');
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('provider').textContent).toBe('claude');
  expect(screen.getByTestId('model').textContent).toBe('sonnet');
});

it('same project id local vs shared creates DISTINCT sessions and readOnly tracks the response', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('readonly').textContent).toBe('false');
  await act(async () => { screen.getByText('startShared').click(); });
  expect(createAssistantSession).toHaveBeenCalledTimes(2); // source in the key → no dedupe
  expect(screen.getByTestId('readonly').textContent).toBe('true');
});

it('surfaces an error when sendMessage POST fails (not silent)', async () => {
  postAssistantMessage.mockRejectedValueOnce(new Error('network down'));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  await act(async () => { screen.getByText('send').click(); });
  expect(screen.getByTestId('error').textContent).toContain('network down');
});

it('surfaces an error when startSession create fails (not silent)', async () => {
  createAssistantSession.mockRejectedValueOnce(new Error('bad provider'));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('error').textContent).toContain('bad provider');
  expect(screen.getByTestId('provider').textContent).toBe('null'); // no session committed
});

it('startSession race: the latest requested context wins even if it resolves first', async () => {
  // First call (pA) resolves LAST; second call (pB) resolves FIRST. The
  // committed session must be pB's — the most recently requested context —
  // not the older pA response arriving later.
  const deferred = {};
  createAssistantSession.mockImplementation((ctx) => new Promise((resolve) => {
    deferred[ctx.projectId] = () => resolve({ sessionId: `sess-${ctx.projectId}` });
  }));
  let hookRef;
  const Grab = () => { hookRef = useAssistantDrawer(); return null; };
  render(<AssistantDrawerProvider><Probe /><Grab /></AssistantDrawerProvider>);

  // Fire both startSession calls without awaiting; neither has resolved yet.
  await act(async () => {
    hookRef.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' });
    hookRef.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' });
  });
  // Resolve pB (latest) first, then pA (older) last.
  await act(async () => { deferred.pB(); await Promise.resolve(); });
  await act(async () => { deferred.pA(); await Promise.resolve(); });

  // The stale pA resolution must be ignored — pB's session stays committed.
  expect(postAssistantMessage).not.toHaveBeenCalled();
  await act(async () => { hookRef.sendMessage('x', {}); });
  expect(postAssistantMessage).toHaveBeenCalledWith('sess-pB', { text: 'x', uiState: {}, webEnabled: false, writeEnabled: false });
});

it('a superseded in-flight commit does not land after the user re-selects the original context (source flip-flop race)', async () => {
  // Regression for the dedupe early-return NOT re-claiming latestKeyRef:
  // start A (commits) -> start B (leave create pending) -> start A again
  // (hits the dedupe path) -> resolve B's stale create. B's resolution must
  // be invalidated and the committed session must still be A's.
  const deferred = {};
  createAssistantSession.mockImplementation((ctx) => new Promise((resolve) => {
    const key = `${ctx.provider}:${ctx.model}:${ctx.projectId}:${ctx.runId}:${ctx.source || 'local'}`;
    deferred[key] = () => resolve({ sessionId: `sess-${key}`, readOnly: ctx.source === 'shared' });
  }));
  let hookRef;
  const Grab = () => { hookRef = useAssistantDrawer(); return null; };
  render(<AssistantDrawerProvider><Probe /><Grab /></AssistantDrawerProvider>);

  const ctxA = { provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' };
  const ctxB = { provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r', source: 'shared' };
  const keyA = 'claude:sonnet:p:r:local';
  const keyB = 'claude:sonnet:p:r:shared';

  // Start A and let it commit.
  await act(async () => { hookRef.startSession(ctxA); });
  await act(async () => { deferred[keyA](); await Promise.resolve(); });
  expect(screen.getByTestId('readonly').textContent).toBe('false');

  // Start B; its create is left pending.
  await act(async () => { hookRef.startSession(ctxB); });

  // The user flips back to A. Same key as the already-committed session, so
  // this hits the dedupe early-return — but it must still re-claim
  // latestKeyRef so B's later resolution can't win.
  await act(async () => { hookRef.startSession(ctxA); });

  // Now let B's stale create resolve.
  await act(async () => { deferred[keyB](); await Promise.resolve(); });

  // B's resolution must have been ignored: still on A's session.
  expect(screen.getByTestId('readonly').textContent).toBe('false');
  await act(async () => { hookRef.sendMessage('x', {}); });
  expect(postAssistantMessage).toHaveBeenCalledWith(`sess-${keyA}`, expect.objectContaining({ text: 'x' }));
});

it('webEnabled toggles, rides the POST body, and resets on a new session', async () => {
  // the race test above swapped in a deferred implementation; clearAllMocks
  // clears calls, not implementations, so restore the default here.
  createAssistantSession.mockImplementation(async () => ({ sessionId: 's1' }));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('web').textContent).toBe('false');
  act(() => { screen.getByText('web').click(); });
  expect(screen.getByTestId('web').textContent).toBe('true');
  await act(async () => { screen.getByText('send').click(); });
  expect(postAssistantMessage).toHaveBeenCalledWith('s1',
    { text: 'hi', uiState: { activeTab: 'overview' }, webEnabled: true, writeEnabled: false });
  // switching context (new session) resets the toggle to off
  await act(async () => { screen.getByText('startA').click(); });
  expect(screen.getByTestId('web').textContent).toBe('false');
});

it('resetConversation mints a fresh session for the same context and clears state', async () => {
  let n = 0;
  createAssistantSession.mockImplementation(async () => ({ sessionId: `s-${++n}` }));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  act(() => { screen.getByText('web').click(); });  // dirty the toggle
  await act(async () => { screen.getByText('reset').click(); });
  expect(createAssistantSession).toHaveBeenCalledTimes(2);
  expect(createAssistantSession).toHaveBeenLastCalledWith(
    { provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' });
  expect(screen.getByTestId('web').textContent).toBe('false');       // toggle reset
  expect(screen.getByTestId('provider').textContent).toBe('claude'); // meta kept
  await act(async () => { screen.getByText('send').click(); });
  expect(postAssistantMessage).toHaveBeenCalledWith('s-2', expect.objectContaining({ text: 'hi' }));
});

it('resetConversation is a no-op while a turn is in flight or before any session', async () => {
  createAssistantSession.mockImplementation(async () => ({ sessionId: 's1' }));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('reset').click(); });  // no session yet
  expect(createAssistantSession).not.toHaveBeenCalled();
  await act(async () => { screen.getByText('start').click(); });
  await act(async () => { screen.getByText('send').click(); });   // turn in flight
  await act(async () => { screen.getByText('reset').click(); });
  expect(createAssistantSession).toHaveBeenCalledTimes(1);
});

it('stopTurn posts a stop for the active session while a turn is in flight', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  await act(async () => { screen.getByText('send').click(); });   // turn in flight
  await act(async () => { screen.getByText('stop').click(); });
  expect(stopAssistantTurn).toHaveBeenCalledWith('s1');
});

it('stopTurn is a no-op when no turn is in flight', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  await act(async () => { screen.getByText('stop').click(); });   // nothing running
  expect(stopAssistantTurn).not.toHaveBeenCalled();
});

it('stopTurn failure surfaces an error instead of dying silently', async () => {
  stopAssistantTurn.mockRejectedValueOnce(new Error('stop failed'));
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  await act(async () => { screen.getByText('send').click(); });
  await act(async () => { screen.getByText('stop').click(); });
  expect(screen.getByTestId('error').textContent).toContain('stop failed');
});
