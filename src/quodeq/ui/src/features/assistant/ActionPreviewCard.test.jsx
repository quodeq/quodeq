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
