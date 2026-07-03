import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { AssistantDrawerProvider, useAssistantDrawer } from './AssistantDrawerProvider.jsx';

vi.mock('../../api/assistant.js', () => ({
  createAssistantSession: vi.fn(async () => ({ sessionId: 's1' })),
  postAssistantMessage: vi.fn(async () => ({ accepted: true })),
  assistantEventsUrl: (id, a) => `/api/assistant/sessions/${id}/events?after=${a}`,
}));
vi.mock('./useAssistantStream.js', () => ({
  useAssistantStream: () => ({ messages: [], streaming: false, error: null, reset: vi.fn() }),
}));
import { createAssistantSession, postAssistantMessage } from '../../api/assistant.js';

function Probe() {
  const d = useAssistantDrawer();
  return (
    <div>
      <span data-testid="open">{String(d.isOpen)}</span>
      <span data-testid="provider">{String(d.provider)}</span>
      <span data-testid="model">{String(d.model)}</span>
      <span data-testid="error">{String(d.error)}</span>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' })}>start</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pA', runId: 'r' })}>startA</button>
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'pB', runId: 'r' })}>startB</button>
      <button onClick={d.toggle}>toggle</button>
      <button onClick={() => d.sendMessage('hi', { activeTab: 'overview' })}>send</button>
    </div>
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => localStorage.clear());

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
  expect(postAssistantMessage).toHaveBeenCalledWith('s1', { text: 'hi', uiState: { activeTab: 'overview' } });
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
  expect(postAssistantMessage).toHaveBeenCalledWith('sess-pB', { text: 'x', uiState: {} });
});
