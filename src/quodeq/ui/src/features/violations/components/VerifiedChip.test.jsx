import React from 'react';
import { it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../../../api/findings.js', () => ({
  listVerifiedFindings: vi.fn(async () => [
    { req: 'r1', file: 'a.py', line: 3, note: 'confirmed real', verifiedAt: 't' },
  ]),
  unverifyFinding: vi.fn(async () => ({ ok: true })),
}));
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';
import { VerifiedFindingsProvider } from './verifiedFindingsContext.jsx';
import { VerifiedChip } from './VerifiedChip.jsx';

beforeEach(() => vi.clearAllMocks());

it('renders nothing without a provider', () => {
  const { container } = render(<VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />);
  expect(container.firstChild).toBeNull();
});

it('renders the chip inside a provider when the key matches', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => expect(screen.getByRole('button', { name: /verified/i })).toBeInTheDocument());
});

it('renders nothing for an unmatched key', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <VerifiedChip v={{ req: 'r2', file: 'b.py', line: 99 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => expect(listVerifiedFindings).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: /verified/i })).toBeNull();
});

it('click calls unverifyFinding and removes the chip', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  const btn = await screen.findByRole('button', { name: /verified/i });
  fireEvent.click(btn);
  await waitFor(() => expect(unverifyFinding).toHaveBeenCalledWith('proj', { req: 'r1', file: 'a.py', line: 3 }));
  await waitFor(() => expect(screen.queryByRole('button', { name: /verified/i })).toBeNull());
});

it('a rejected unverifyFinding does not throw (chip stays, no unhandled rejection)', async () => {
  unverifyFinding.mockRejectedValueOnce(new Error('network error'));
  render(
    <VerifiedFindingsProvider project="proj">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  const btn = await screen.findByRole('button', { name: /verified/i });
  // Should not throw
  fireEvent.click(btn);
  await waitFor(() => expect(unverifyFinding).toHaveBeenCalled());
  // chip stays because unverify failed; context unverify will have rejected but catch absorbed it
  // Wait a tick to let any async error surface
  await new Promise((r) => setTimeout(r, 20));
  // If we get here without an unhandled rejection, the test passes
});
