import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CloneProgress from './CloneProgress.jsx';
import { SYNC_PHASE } from '../../../../vocab/syncPhase.js';
import { ApiProvider } from '../../../../api/ApiContext.jsx';

const URL = 'https://github.com/acme/billing.git';
const idle = { run: vi.fn(), pending: false, slot: null, attachedElsewhere: false, accessFailure: null, startError: null, cloneError: null };
const following = (slot, extra = {}) => ({ ...idle, pending: true, slot, ...extra });

describe('CloneProgress', () => {
  it('renders nothing while there is no clone to show', () => {
    const { container } = render(<CloneProgress launch={idle} url={URL} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the download with its percent and size', () => {
    render(<CloneProgress launch={following({ phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912 })} url={URL} />);
    expect(screen.getByText('cloning · 45% · 12.0 MB')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'clone progress' })).toHaveAttribute('aria-valuenow', '45');
  });

  it('reads "cloning…" with an indeterminate bar until a percent comes', () => {
    render(<CloneProgress launch={following({ phase: SYNC_PHASE.DOWNLOADING, percent: null, bytes: 0 })} url={URL} />);
    expect(screen.getByText('cloning…')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-busy', 'true');
  });

  it('a percent with no size yet leaves the size out', () => {
    render(<CloneProgress launch={following({ phase: SYNC_PHASE.DOWNLOADING, percent: 3, bytes: 0 })} url={URL} />);
    expect(screen.getByText('cloning · 3%')).toBeInTheDocument();
  });

  it('shows the file walk once the download is done', () => {
    render(<CloneProgress launch={following({ phase: SYNC_PHASE.READING })} url={URL} />);
    expect(screen.getByText('walking files · detecting languages…')).toBeInTheDocument();
  });

  it('a clone already running elsewhere says so', () => {
    render(<CloneProgress launch={following({ phase: SYNC_PHASE.DOWNLOADING, percent: 10, bytes: 2048 }, { attachedElsewhere: true })} url={URL} />);
    expect(screen.getByText('a clone is already running, waiting for it to finish')).toBeInTheDocument();
  });

  it('the error row shows the message and git output, and retry retries', () => {
    const retry = vi.fn();
    render(<CloneProgress launch={{ ...idle, cloneError: { message: 'could not clone the repository', detail: 'fatal: nope', retry } }} url={URL} />);
    expect(screen.getByRole('alert')).toHaveTextContent('could not clone the repository');
    expect(screen.getByText('fatal: nope')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('an unreachable url shows the access panel instead', () => {
    const api = { probeGit: vi.fn(), getGithubAccount: vi.fn(async () => null) };
    const failure = { kind: 'network', detail: '', host: 'github.com', isGitHub: false };
    render(<ApiProvider value={api}><CloneProgress launch={{ ...idle, accessFailure: failure }} url={URL} /></ApiProvider>);
    expect(screen.getByRole('region')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});
