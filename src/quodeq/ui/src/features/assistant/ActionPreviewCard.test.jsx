import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ActionPreviewCard } from './ActionPreviewCard.jsx';

vi.mock('../../api/assistant.js', () => ({
  applyAssistantAction: vi.fn(async () => ({ applied: true })),
  rejectAssistantAction: vi.fn(async () => ({ status: 'rejected' })),
}));
import { applyAssistantAction, rejectAssistantAction } from '../../api/assistant.js';

const action = { actionId: 'a1', actionType: 'create_standard',
  summary: { id: 'rfc7807', name: 'RFC7807 Errors', principleCount: 3 } };

beforeEach(() => vi.clearAllMocks());

it('renders the canonical summary, not raw markdown', () => {
  render(<ActionPreviewCard action={action} />);
  expect(screen.getByText('RFC7807 Errors')).toBeInTheDocument();
  expect(screen.getByText(/3 principles/i)).toBeInTheDocument();
});

it('apply calls the endpoint and shows applied', async () => {
  render(<ActionPreviewCard action={action} />);
  fireEvent.click(screen.getByRole('button', { name: /apply/i }));
  await waitFor(() => expect(applyAssistantAction).toHaveBeenCalledWith('a1'));
  expect(await screen.findByText(/applied/i)).toBeInTheDocument();
});

it('reject calls the endpoint and shows rejected', async () => {
  render(<ActionPreviewCard action={action} />);
  fireEvent.click(screen.getByRole('button', { name: /reject/i }));
  await waitFor(() => expect(rejectAssistantAction).toHaveBeenCalledWith('a1'));
  expect(await screen.findByText(/rejected/i)).toBeInTheDocument();
});

it('renders a dismiss_finding summary', () => {
  render(<ActionPreviewCard action={{ actionId: 'a1', actionType: 'dismiss_finding',
    summary: { req: 'r1', file: 'a.py', line: 3, reason: 'guarded above' } }} />);
  expect(screen.getByText('Dismiss finding')).toBeInTheDocument();
  expect(screen.getByText(/r1 · a\.py:3/)).toBeInTheDocument();
  expect(screen.getByText('guarded above')).toBeInTheDocument();
});

it('renders a verify_finding summary', () => {
  render(<ActionPreviewCard action={{ actionId: 'a2', actionType: 'verify_finding',
    summary: { req: 'r1', file: 'a.py', line: 3, note: 'real, unsanitized input' } }} />);
  expect(screen.getByText('Mark finding as verified')).toBeInTheDocument();
  expect(screen.getByText('real, unsanitized input')).toBeInTheDocument();
});

it('dispatches quodeq:assistant-action-applied on successful apply', async () => {
  const events = [];
  const handler = (e) => events.push(e);
  window.addEventListener('quodeq:assistant-action-applied', handler);
  const dismissAction = { actionId: 'a3', actionType: 'dismiss_finding',
    summary: { req: 'r1', file: 'a.py', line: 3, reason: 'fp' } };
  render(<ActionPreviewCard action={dismissAction} />);
  fireEvent.click(screen.getByRole('button', { name: /apply/i }));
  await waitFor(() => expect(applyAssistantAction).toHaveBeenCalledWith('a3'));
  await waitFor(() => expect(events.length).toBe(1));
  expect(events[0].detail.actionType).toBe('dismiss_finding');
  window.removeEventListener('quodeq:assistant-action-applied', handler);
});
