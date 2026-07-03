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
      <button onClick={() => d.startSession({ provider: 'claude', model: 'sonnet', projectId: 'p', runId: 'r' })}>start</button>
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
