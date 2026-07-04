import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AssistantDrawerProvider, useAssistantDrawer } from './AssistantDrawerProvider.jsx';

vi.mock('../../api/assistant.js', () => ({
  createAssistantSession: vi.fn(async () => ({ sessionId: 's1' })),
  postAssistantMessage: vi.fn(async () => ({ accepted: true })),
  assistantEventsUrl: (id, a) => `/api/assistant/sessions/${id}/events?after=${a}`,
}));
const _streamHooks = { onDone: null };
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: (_sessionId, opts) => {
    _streamHooks.onDone = opts?.onDone || null;  // capture so tests can fire it
    return { messages: [], streaming: false, error: null, reset: vi.fn() };
  },
}));
import { createAssistantSession, postAssistantMessage } from '../../api/assistant.js';

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
      <button onClick={d.toggleWebEnabled}>web</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' })}>start</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' })}>startA</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' })}>startB</button>
      <button onClick={d.toggle}>toggle</button>
      <button onClick={() => d.sendMessage('hi', { activeTab: 'overview' })}>send</button>
      <button onClick={d.resetConversation}>reset</button>
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

it('exposes activeTab defaulting to assistant; openTab switches the active tab', () => {
  // Both features enabled so the per-tab disable-fallback effect doesn't
  // reroute the initial tab.
  localStorage.setItem('cc-assistant-enabled', 'true');
  localStorage.setItem('cc-terminal-enabled', 'true');
  let hookRef;
  const Grab = () => { hookRef = useAssistantDrawer(); return null; };
  render(<AssistantDrawerProvider><Grab /></AssistantDrawerProvider>);
  expect(hookRef.activeTab).toBe('assistant');
  act(() => hookRef.openTab('terminal'));
  expect(hookRef.activeTab).toBe('terminal');
});

it('startSession creates a session; sendMessage posts to it', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  await act(async () => { screen.getByText('start').click(); });
  expect(createAssistantSession).toHaveBeenCalledWith({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' });
  await act(async () => { screen.getByText('send').click(); });
  expect(postAssistantMessage).toHaveBeenCalledWith('s1', { text: 'hi', uiState: { activeTab: 'overview' }, webEnabled: false });
});

it('exposes the active session provider/model for the drawer header', async () => {
  render(<AssistantDrawerProvider><Probe /></AssistantDrawerProvider>);
  expect(screen.getByTestId('provider').textContent).toBe('null');
  expect(screen.getByTestId('model').textContent).toBe('null');
  await act(async () => { screen.getByText('start').click(); });
  expect(screen.getByTestId('provider').textContent).toBe('claude');
  expect(screen.getByTestId('model').textContent).toBe('sonnet');
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
  expect(postAssistantMessage).toHaveBeenCalledWith('sess-pB', { text: 'x', uiState: {}, webEnabled: false });
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
    { text: 'hi', uiState: { activeTab: 'overview' }, webEnabled: true });
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
