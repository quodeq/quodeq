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
vi.mock('../../../api/shared.js', () => ({
  sharedListVerifiedFindings: vi.fn(async () => [
    { req: 'r1', file: 'a.py', line: 3, note: 'confirmed real', verifiedAt: 't' },
  ]),
}));
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';
import { sharedListVerifiedFindings } from '../../../api/shared.js';
import { VerifiedFindingsProvider } from './verifiedFindingsContext.jsx';
import { VerifiedChip } from './VerifiedChip.jsx';

beforeEach(() => vi.clearAllMocks());

it('renders nothing without a provider', () => {
  const { container } = render(<VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />);
  expect(container.firstChild).toBeNull();
});

it('renders an icon-only chip inside a provider when the key matches', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  const btn = await screen.findByRole('button', { name: /verified/i });
  // Icon-only: named via aria-label (note included), no visible text, an svg check.
  expect(btn).toHaveAccessibleName(/confirmed real/i);
  expect(btn.textContent).toBe('');
  expect(btn.querySelector('svg')).toBeInTheDocument();
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

// Shared projects have no unverify route on the backend (Task 19's
// verifiedFindingsContext already no-ops unverify for `source="shared"`).
// The chip must still surface the badge (read-only), but as a
// non-interactive element so there's no dead-end click affordance.
it('renders a non-interactive chip (no button role, no click) when source is shared', async () => {
  render(
    <VerifiedFindingsProvider project="proj" source="shared">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => expect(sharedListVerifiedFindings).toHaveBeenCalledWith('proj'));
  await waitFor(() => expect(screen.queryByLabelText(/verified/i)).toBeInTheDocument());
  expect(screen.queryByRole('button')).toBeNull();
  const chip = screen.getByLabelText(/verified/i);
  expect(chip.tagName).toBe('SPAN');
  fireEvent.click(chip);
  expect(unverifyFinding).not.toHaveBeenCalled();
});

it('renders a clickable button chip when source is local', async () => {
  render(
    <VerifiedFindingsProvider project="proj" source="local">
      <VerifiedChip v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  const btn = await screen.findByRole('button', { name: /verified/i });
  expect(btn.tagName).toBe('BUTTON');
});

it('a rejected unverifyFinding warns instead of failing silently (chip stays, no unhandled rejection)', async () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
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
  await waitFor(() => expect(warn).toHaveBeenCalledWith('unverify failed:', expect.any(Error)));
  // chip stays because unverify failed; context unverify will have rejected but catch absorbed it
  expect(screen.getByRole('button', { name: /verified/i })).toBeInTheDocument();
  warn.mockRestore();
});
