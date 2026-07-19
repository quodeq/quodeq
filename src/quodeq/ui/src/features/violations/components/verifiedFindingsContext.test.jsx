import React from 'react';
import { it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../../../api/findings.js', () => ({
  listVerifiedFindings: vi.fn(async () => [
    { req: 'r1', file: 'a.py', line: 3, note: 'checked', verifiedAt: 't' },
  ]),
  unverifyFinding: vi.fn(async () => ({ ok: true })),
}));
vi.mock('../../../api/shared.js', () => ({
  sharedListVerifiedFindings: vi.fn(async () => []),
}));
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';
import { sharedListVerifiedFindings } from '../../../api/shared.js';
import { VerifiedFindingsProvider, useVerifiedFindings } from './verifiedFindingsContext.jsx';

beforeEach(() => vi.clearAllMocks());

function Probe({ v }) {
  const ctx = useVerifiedFindings();
  const key = `${v.req || ''}|${v.file || ''}|${v.line || 0}`;
  if (!ctx?.keys?.has(key)) return <div>not verified</div>;
  return (
    <button type="button" onClick={() => ctx.unverify(v)}>{ctx.noteFor(key)}</button>
  );
}

it('exposes fetched keys and notes', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => expect(screen.getByText('checked')).toBeInTheDocument());
  expect(listVerifiedFindings).toHaveBeenCalledWith('proj');
});

it('unverify removes the key locally', async () => {
  render(
    <VerifiedFindingsProvider project="proj">
      <Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => screen.getByText('checked'));
  fireEvent.click(screen.getByText('checked'));
  await waitFor(() => expect(screen.getByText('not verified')).toBeInTheDocument());
  expect(unverifyFinding).toHaveBeenCalledWith('proj', { req: 'r1', file: 'a.py', line: 3 });
});

it('returns null without a provider', () => {
  render(<Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />);
  expect(screen.getByText('not verified')).toBeInTheDocument();
});

// Shared projects have no mutation routes on the backend (unverify is
// local-only by design, same as dismiss/restore/delete). The badge list must
// read from the shared-repo mirror endpoint, and unverify must no-op even if
// a click handler somehow invokes it — defense in depth against corrupting
// the local cache with a shared-derived id collision.
it('reads verified entries via the shared endpoint when source is shared', async () => {
  sharedListVerifiedFindings.mockResolvedValueOnce([
    { req: 'r1', file: 'a.py', line: 3, note: 'from shared', verifiedAt: 't' },
  ]);
  render(
    <VerifiedFindingsProvider project="proj" source="shared">
      <Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => expect(screen.getByText('from shared')).toBeInTheDocument());
  expect(sharedListVerifiedFindings).toHaveBeenCalledWith('proj');
  expect(listVerifiedFindings).not.toHaveBeenCalled();
});

it('unverify no-ops and never calls the local unverify endpoint when source is shared', async () => {
  sharedListVerifiedFindings.mockResolvedValueOnce([
    { req: 'r1', file: 'a.py', line: 3, note: 'from shared', verifiedAt: 't' },
  ]);
  render(
    <VerifiedFindingsProvider project="proj" source="shared">
      <Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  await waitFor(() => screen.getByText('from shared'));
  fireEvent.click(screen.getByText('from shared'));
  // Give any (unwanted) async work a tick to settle, then assert the badge
  // is still present — a real unverify would have removed it.
  await act(async () => {});
  expect(unverifyFinding).not.toHaveBeenCalled();
  expect(screen.getByText('from shared')).toBeInTheDocument();
});

it('refetches when quodeq:assistant-action-applied fires with verify_finding', async () => {
  listVerifiedFindings.mockResolvedValueOnce([])
    .mockResolvedValueOnce([{ req: 'r1', file: 'a.py', line: 3, note: 'checked', verifiedAt: 't' }]);
  render(
    <VerifiedFindingsProvider project="proj">
      <Probe v={{ req: 'r1', file: 'a.py', line: 3 }} />
    </VerifiedFindingsProvider>,
  );
  // initial fetch returned empty list
  await waitFor(() => expect(listVerifiedFindings).toHaveBeenCalledTimes(1));
  expect(screen.getByText('not verified')).toBeInTheDocument();
  // fire the window event
  await act(async () => {
    window.dispatchEvent(new CustomEvent('quodeq:assistant-action-applied', {
      detail: { actionType: 'verify_finding' },
    }));
  });
  await waitFor(() => expect(listVerifiedFindings).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByText('checked')).toBeInTheDocument());
});
