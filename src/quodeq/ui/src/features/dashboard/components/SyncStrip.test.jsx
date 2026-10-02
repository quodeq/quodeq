import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import SyncStrip from './SyncStrip.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';

const idle = { state: 'idle', phase: null };
const base = { configured: true, url: 'https://github.com/quodeq/evaluations', lastSynced: Date.now() - 120000, connect: idle, refresh: idle, pull: idle };

describe('SyncStrip', () => {
  it('shows downloading with a bar', () => {
    render(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912 } }} projectsCount={0} />);
    expect(screen.getByText(/downloading evaluations · 45% · 12.0 MB/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45');
  });
  it('shows reading with the count', () => {
    render(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 3 } }} projectsCount={0} />);
    expect(screen.getByText(/reading projects · 3 found/)).toBeInTheDocument();
  });
  it('shows synced with count and when, plus the actions', () => {
    const onUpdate = vi.fn(); const onCopyInvite = vi.fn();
    render(<SyncStrip status={base} projectsCount={5} onUpdate={onUpdate} onCopyInvite={onCopyInvite} />);
    expect(screen.getByText(/5 projects · synced 2 min ago/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /update/i })); expect(onUpdate).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /copy invite/i })); expect(onCopyInvite).toHaveBeenCalled();
  });
  it('shows update failed with retry and keeps the when', () => {
    const onUpdate = vi.fn();
    render(<SyncStrip status={{ ...base, refresh: { state: 'error', phase: SYNC_PHASE.ERROR, error: 'Could not resolve host', code: 'REFRESH_FAILED' } }} projectsCount={5} onUpdate={onUpdate} />);
    expect(screen.getByText(/update failed · showing results from 2 min ago/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i })); expect(onUpdate).toHaveBeenCalled();
  });
  it('renders nothing when not configured', () => {
    const { container } = render(<SyncStrip status={{ ...base, configured: false }} projectsCount={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  // Beyond the brief's five: the remaining rows of the spec's table (4.2).
  it('shows connecting to the host/path with an indeterminate bar, even before the repo is configured', () => {
    const status = { ...base, configured: false, url: null, lastSynced: null, connect: { state: 'running', phase: SYNC_PHASE.CONNECTING, percent: null, url: 'https://github.com/quodeq/evaluations.git' } };
    render(<SyncStrip status={status} projectsCount={0} />);
    expect(screen.getByText('connecting to github.com/quodeq/evaluations…')).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-busy', 'true');
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });
  it('shows downloading without a size when the job has not counted bytes', () => {
    render(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: null, bytes: null } }} projectsCount={0} />);
    expect(screen.getByText('downloading evaluations…')).toBeInTheDocument();
  });
  it('formats a size under 1 MB in KB', () => {
    render(<SyncStrip status={{ ...base, refresh: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 10, bytes: 2048 } }} projectsCount={0} />);
    expect(screen.getByText(/downloading evaluations · 10% · 2 KB/)).toBeInTheDocument();
  });
  it('shows updating while a refresh connects, and no update button', () => {
    render(<SyncStrip status={{ ...base, refresh: { state: 'running', phase: SYNC_PHASE.CONNECTING } }} projectsCount={5} onUpdate={vi.fn()} />);
    expect(screen.getByText('updating…')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('button', { name: /update/i })).not.toBeInTheDocument();
  });
  it('a running connect outranks a failed refresh', () => {
    const status = { ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 2 }, refresh: { state: 'error', phase: SYNC_PHASE.ERROR } };
    render(<SyncStrip status={status} projectsCount={5} />);
    expect(screen.getByText(/reading projects · 2 found/)).toBeInTheDocument();
    expect(screen.queryByText(/update failed/)).not.toBeInTheDocument();
  });
  it('shows a failed connect with its mapped copy and a retry', () => {
    const onRetryConnect = vi.fn();
    render(<SyncStrip status={{ ...base, connect: { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO', error: 'raw' } }} projectsCount={5} onRetryConnect={onRetryConnect} />);
    expect(screen.getByText(/That repository belongs to a different project\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i })); expect(onRetryConnect).toHaveBeenCalled();
  });
  it('shows offline with the last sync when the status poll fails', () => {
    render(<SyncStrip status={base} offline projectsCount={5} onUpdate={vi.fn()} />);
    expect(screen.getByText('offline · showing results from 2 min ago')).toBeInTheDocument();
    expect(screen.queryByText(/synced/)).not.toBeInTheDocument();
  });
  it('flashes copied after a copy and shows the invite inline when the clipboard is unavailable', () => {
    const { rerender } = render(<SyncStrip status={base} projectsCount={5} invite={{ copied: true }} />);
    expect(screen.getByRole('button', { name: 'copied' })).toBeInTheDocument();
    rerender(<SyncStrip status={base} projectsCount={5} invite={{ fallbackText: 'Open quodeq, paste x' }} />);
    expect(screen.getByDisplayValue('Open quodeq, paste x')).toHaveAttribute('readonly');
  });
  it('the ⋯ menu offers change repository and disconnect', () => {
    const onChange = vi.fn(); const onDisconnect = vi.fn();
    render(<SyncStrip status={base} projectsCount={5} onChange={onChange} onDisconnect={onDisconnect} />);
    fireEvent.click(screen.getByRole('button', { name: /more repository actions/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'change repository' })); expect(onChange).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /more repository actions/i }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'disconnect' })); expect(onDisconnect).toHaveBeenCalled();
  });
  it('shows the repository as host/path', () => {
    render(<SyncStrip status={base} projectsCount={5} />);
    expect(screen.getByText('github.com/quodeq/evaluations')).toBeInTheDocument();
  });
});
