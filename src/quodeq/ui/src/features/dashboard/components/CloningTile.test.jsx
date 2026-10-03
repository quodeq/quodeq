import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CloningTile from './CloningTile.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';

const running = {
  state: 'running', kind: 'clone', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912,
  repo: 'https://github.com/acme/billing.git', dest: '/u/quodeq/repos/billing', finishedAt: null,
};

describe('CloningTile', () => {
  it('names the incoming project and shows the bar', () => {
    render(<CloningTile slot={running} onRetry={() => {}} onClose={() => {}} />);
    expect(screen.getByText('billing')).toBeInTheDocument();
    expect(screen.getByText('cloning · 45% · 12.0 MB')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  });

  it('prefers the registered project name once the server knows it', () => {
    render(<CloningTile slot={{ ...running, projectName: 'Billing API' }} onRetry={() => {}} onClose={() => {}} />);
    expect(screen.getByText('Billing API')).toBeInTheDocument();
  });

  it('reading shows the file walk copy with an indeterminate bar', () => {
    render(<CloningTile slot={{ ...running, phase: SYNC_PHASE.READING, percent: null }} onRetry={() => {}} onClose={() => {}} />);
    expect(screen.getByText('walking files · detecting languages…')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-busy', 'true');
  });

  it('a failed clone shows the reason, retry and close', () => {
    const onRetry = vi.fn();
    const onClose = vi.fn();
    const slot = { ...running, state: 'error', phase: SYNC_PHASE.ERROR, code: 'REPO_NOT_FOUND', error: 'Repository not found', finishedAt: 5 };
    render(<CloningTile slot={slot} onRetry={onRetry} onClose={onClose} />);
    expect(screen.getByText(/download failed · /)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(onRetry).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    expect(onClose).toHaveBeenCalled();
  });
});
