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
  it('shows how many cards are ready while the server is still warming the rest, with an indeterminate bar', () => {
    render(<SyncStrip status={base} projectsCount={1} warming={{ active: true, done: 1, total: 4, remaining: 3 }} />);
    expect(screen.getByText('loading results · 1 of 4 ready…', { selector: '.sync-strip__meta' })).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('loading results…');
    expect(screen.queryByRole('button', { name: /update/i })).not.toBeInTheDocument();
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
    expect(screen.getByText('connecting to github.com/quodeq/evaluations…', { selector: '.sync-strip__meta' })).toBeInTheDocument();
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-busy', 'true');
    expect(bar).not.toHaveAttribute('aria-valuenow');
  });
  it('shows downloading without a size when the job has not counted bytes', () => {
    render(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: null, bytes: null } }} projectsCount={0} />);
    expect(screen.getByText('downloading evaluations…', { selector: '.sync-strip__meta' })).toBeInTheDocument();
  });
  it('formats a size under 1 MB in KB', () => {
    render(<SyncStrip status={{ ...base, refresh: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 10, bytes: 2048 } }} projectsCount={0} />);
    expect(screen.getByText(/downloading evaluations · 10% · 2 KB/)).toBeInTheDocument();
  });
  it('shows updating while a refresh connects, and no update button', () => {
    render(<SyncStrip status={{ ...base, refresh: { state: 'running', phase: SYNC_PHASE.CONNECTING } }} projectsCount={5} onUpdate={vi.fn()} />);
    expect(screen.getByText('updating…', { selector: '.sync-strip__meta' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('button', { name: /update/i })).not.toBeInTheDocument();
  });
  it('a running connect outranks a failed refresh', () => {
    const status = { ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 2 }, refresh: { state: 'error', phase: SYNC_PHASE.ERROR } };
    render(<SyncStrip status={status} projectsCount={5} />);
    expect(screen.getByText(/reading projects · 2 found/)).toBeInTheDocument();
    expect(screen.queryByText(/update failed/)).not.toBeInTheDocument();
  });
  // A failed connect is the connect card's to report (pickStripState): with a
  // repository configured the strip keeps describing the one that still works.
  it('a failed change of repository leaves the strip on synced, with the count and the update action', () => {
    const onUpdate = vi.fn();
    render(<SyncStrip status={{ ...base, connect: { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO', error: 'raw' } }} projectsCount={5} onUpdate={onUpdate} />);
    expect(screen.getByText('5 projects · synced 2 min ago')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'update evaluations repository' })).toBeInTheDocument();
    expect(screen.queryByText(/not a quodeq evaluations repository/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'retry' })).not.toBeInTheDocument();
  });
  it('a failed first connect renders no strip (the card carries the error)', () => {
    const { container } = render(<SyncStrip status={{ ...base, configured: false, url: null, connect: { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO' } }} projectsCount={0} />);
    expect(container).toBeEmptyDOMElement();
  });
  it('a failure row without a retry handler ends without a dangling separator', () => {
    const refreshFailed = { ...base, refresh: { state: 'error', phase: SYNC_PHASE.ERROR } };
    const { container, rerender } = render(<SyncStrip status={refreshFailed} projectsCount={5} />);
    const row = () => container.querySelector('.sync-strip__meta');
    expect(row().textContent).toMatch(/2 min ago$/);
    expect(screen.queryByRole('button', { name: 'retry' })).not.toBeInTheDocument();
    rerender(<SyncStrip status={base} loadFailed projectsCount={5} />);
    expect(row().textContent).toBe('could not read the evaluations repository');
    rerender(<SyncStrip status={refreshFailed} projectsCount={5} onUpdate={vi.fn()} />);
    expect(row().textContent).toMatch(/2 min ago · retry$/);
  });
  it('announces only the phase while a job runs, not every percent', () => {
    const { rerender } = render(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912 } }} projectsCount={0} />);
    expect(screen.getByRole('status')).toHaveTextContent('downloading evaluations…');
    rerender(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 46, bytes: 12682912 } }} projectsCount={0} />);
    expect(screen.getByRole('status')).toHaveTextContent('downloading evaluations…');
    rerender(<SyncStrip status={{ ...base, connect: { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 2 } }} projectsCount={0} />);
    expect(screen.getByRole('status')).toHaveTextContent('reading projects…');
    rerender(<SyncStrip status={base} projectsCount={5} />);
    expect(screen.getByRole('status')).toHaveTextContent('5 projects · synced 2 min ago');
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
  it('the ⋯ menu holds exactly change repository and disconnect (import lives in the header)', () => {
    render(<SyncStrip status={base} projectsCount={5} onChange={() => {}} onDisconnect={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /more repository actions/i }));
    expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['change repository', 'disconnect']);
  });
  it('shows the repository as host/path', () => {
    render(<SyncStrip status={base} projectsCount={5} />);
    expect(screen.getByText('github.com/quodeq/evaluations')).toBeInTheDocument();
  });
});
