import React from 'react';
import { it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../../../api/findings.js', () => ({
  listVerifiedFindings: vi.fn(async () => [
    { req: 'r1', file: 'a.py', line: 3, note: 'checked', verifiedAt: 't' },
  ]),
  unverifyFinding: vi.fn(async () => ({ ok: true })),
}));
import { listVerifiedFindings, unverifyFinding } from '../../../api/findings.js';
import { VerifiedFindingsProvider, useVerifiedFindings } from './verifiedFindingsContext.jsx';

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
