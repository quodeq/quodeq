import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { NEW_FINDINGS_ONLY_KEY } from '../../settings/hooks/useLiveFeedSettings.js';

// ScanProgress reads EvalLogContext directly (no provider here), so it stays
// mocked like JobStatStrip. LiveViolationsFeed is left real below: the
// live-findings-filter tests assert on what it renders.
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
// Probe instead of a null stub: renders the total violation count the strip
// actually received, so a regression that reverts EvaluationStatus to pass
// the unfiltered liveViolations to the strip (while the feed stays filtered)
// shows up here instead of leaving every test green.
vi.mock('./JobStatStrip.jsx', () => ({
  default: ({ liveViolations }) => <i data-testid="strip-sum">{
    Object.values(liveViolations || {}).reduce((n, vs) => n + (vs?.length || 0), 0)
  }</i>,
}));
// The identity strip reads the shared progress query for its "mode" cell;
// LiveViolationsFeed reads the same query for its streaming footer/header.
vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn().mockResolvedValue({ dimensions: [] }),
}));

function renderWithClient(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseJob = {
  jobId: 'ext-test',
  status: 'done',
  source: 'external',
  logs: [],
  dimensions: [],
};

describe('JobIdentityStrip', () => {
  it('renders the job ID with a copy button', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, jobId: 'job-123' }} />);
    expect(screen.getByText('job-123')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy job id/i })).toBeInTheDocument();
  });

  it('renders job-runtime-chip when both aiProvider and aiModel are present', () => {
    renderWithClient(
      <EvaluationStatus
        job={{ ...baseJob, aiProvider: 'llamacpp', aiModel: 'qwen3.6-27b' }}
      />
    );
    expect(screen.getByTestId('job-runtime-chip')).toHaveTextContent('llamacpp · qwen3.6-27b');
  });

  it('does not render job-runtime-chip when aiModel is absent', () => {
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, aiProvider: 'llamacpp' }} />
    );
    expect(screen.queryByTestId('job-runtime-chip')).toBeNull();
  });

  it('does not render job-runtime-chip when aiProvider is absent', () => {
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, aiModel: 'qwen3.6-27b' }} />
    );
    expect(screen.queryByTestId('job-runtime-chip')).toBeNull();
  });

  it('renders the model chip in its own labelled identity cell', () => {
    renderWithClient(
      <EvaluationStatus
        job={{ ...baseJob, aiProvider: 'llamacpp', aiModel: 'qwen3.6-27b' }}
      />,
    );
    const chip = screen.getByTestId('job-runtime-chip');
    const cell = chip.closest('.eval-identity__cell');
    expect(cell).not.toBeNull();
    expect(cell.textContent).toMatch(/model/);
    // The chip lives in the strip, not in the job-id cell.
    expect(cell.textContent).not.toMatch(/ext-test/);
  });
});

describe('JobHeader time-limit exit', () => {
  it('renders a deadline-killed job as time limit reached, not failed', () => {
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, status: 'cancelled', exitReason: 'deadline' }} />
    );
    expect(screen.getByText('evaluation_time_limit')).toBeInTheDocument();
    expect(screen.getByText('time limit reached')).toBeInTheDocument();
    // Non-error styling, consistent with the coverage banner below.
    expect(document.querySelector('.eval-run-pill--failed')).toBeNull();
    expect(document.querySelector('.eval-run-pill--neutral')).not.toBeNull();
  });

  it('treats a failed status with a time_limit reason the same way', () => {
    // Defensive: external index rows can end "failed" while status.json
    // still records the time budget as the cause.
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, status: 'failed', exitReason: 'time_limit' }} />
    );
    expect(screen.getByText('evaluation_time_limit')).toBeInTheDocument();
    expect(screen.getByText('time limit reached')).toBeInTheDocument();
    expect(document.querySelector('.eval-run-pill--failed')).toBeNull();
  });

  it('still renders plain failures as failed', () => {
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, status: 'failed' }} />
    );
    expect(screen.getByText('evaluation_failed')).toBeInTheDocument();
    expect(document.querySelector('.eval-run-pill--failed')).not.toBeNull();
  });

  it('keeps a truncated-but-done run rendered as complete', () => {
    // rc=0 deadline truncation: results exist and were scored; the banner
    // below tells the truncation story, the header stays "done".
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, status: 'done', exitReason: 'deadline' }} />
    );
    expect(screen.getByText('evaluation_complete')).toBeInTheDocument();
    expect(screen.queryByText('time limit reached')).toBeNull();
  });

  it('keeps a user-cancelled job rendered as cancelled', () => {
    renderWithClient(
      <EvaluationStatus job={{ ...baseJob, status: 'cancelled' }} />
    );
    expect(screen.getByText('evaluation_cancelled')).toBeInTheDocument();
    expect(screen.queryByText('time limit reached')).toBeNull();
  });
});

describe('project label', () => {
  const startedInfo = { id: 'uuid-c', name: 'project-c', displayName: 'Project C' };
  const jobInfo = { id: 'uuid-a', name: 'project-a', displayName: 'Project A' };

  it("shows the running job's own project when resolvable", () => {
    renderWithClient(
      <EvaluationStatus
        job={{ ...baseJob, status: 'running', outputProject: 'uuid-a' }}
        jobProjectInfo={jobInfo}
        startedProjectInfo={startedInfo}
      />
    );
    expect(screen.getByText('Project A')).toBeInTheDocument();
    expect(screen.queryByText('Project C')).toBeNull();
  });

  it("falls back to the project the job was started for before the report-path marker fires", () => {
    renderWithClient(
      <EvaluationStatus
        job={{ ...baseJob, status: 'running' }}
        jobProjectInfo={null}
        startedProjectInfo={startedInfo}
      />
    );
    expect(screen.getByText('Project C')).toBeInTheDocument();
  });

  it('never labels the card with the globally-selected project', () => {
    // Regression (v1.6.0): the card used to fall back to the UI's global
    // selection, so switching projects mid-run showed the wrong name on a
    // running evaluation. When the job's project is unknown, show nothing.
    renderWithClient(
      <EvaluationStatus
        job={{ ...baseJob, status: 'running' }}
        jobProjectInfo={null}
        startedProjectInfo={null}
      />
    );
    expect(screen.queryByText(/Project [ABC]/)).toBeNull();
    // The repository cell shows a dash instead — unknown beats wrong.
    const strip = document.querySelector('.eval-identity');
    expect(strip.textContent).toMatch(/repository—/);
  });
});

const filterJob = { jobId: 'j1', status: 'running', dimensions: ['security'] };

const filterLiveViolations = {
  security: [
    { severity: 'major', principle: 'P1', file: 'new.py', line: 1, carriedForward: false },
    { severity: 'major', principle: 'P2', file: 'old-a.py', line: 2, carriedForward: true },
    { severity: 'minor', principle: 'P3', file: 'old-b.py', line: 3, carriedForward: true },
  ],
};

function renderStatus(props = {}) {
  const QC = withQueryClient();
  return render(
    <QC><EvaluationStatus job={filterJob} liveViolations={filterLiveViolations} {...props} /></QC>
  );
}

describe('EvaluationStatus live-findings filter', () => {
  beforeEach(() => { localStorage.clear(); });

  it('hides carried-forward findings by default', () => {
    renderStatus();
    expect(screen.getByText('new.py:1')).toBeInTheDocument();
    expect(screen.queryByText('old-a.py:2')).not.toBeInTheDocument();
    // The strip must see the same filtered set as the feed (1 fresh of 3).
    expect(screen.getByTestId('strip-sum')).toHaveTextContent('1');
  });

  it('discloses how many are hidden rather than hiding them silently', () => {
    renderStatus();
    expect(screen.getByText(/2 carried forward hidden/)).toBeInTheDocument();
  });

  it('shows everything when the preference is off', () => {
    localStorage.setItem(NEW_FINDINGS_ONLY_KEY, 'false');
    renderStatus();
    expect(screen.getByText('old-a.py:2')).toBeInTheDocument();
    expect(screen.queryByText(/carried forward hidden/)).not.toBeInTheDocument();
    expect(screen.getByTestId('strip-sum')).toHaveTextContent('3');
  });

  it('hides snake_case carried_forward findings too (SSE payloads with no violation-model mapping)', () => {
    // Under VITE_USE_SSE_EVENTS, findings land in the cache as raw wire
    // payloads, so they carry `carried_forward` instead of `carriedForward`.
    const QC = withQueryClient();
    render(
      <QC>
        <EvaluationStatus
          job={filterJob}
          liveViolations={{
            security: [
              { severity: 'major', principle: 'P1', file: 'new.py', line: 1, carried_forward: false },
              { severity: 'major', principle: 'P2', file: 'old-a.py', line: 2, carried_forward: true },
            ],
          }}
        />
      </QC>
    );
    expect(screen.getByText('new.py:1')).toBeInTheDocument();
    expect(screen.queryByText('old-a.py:2')).not.toBeInTheDocument();
    expect(screen.getByText(/1 carried forward hidden/)).toBeInTheDocument();
  });

  it('says nothing about carries when the run has none', () => {
    const QC = withQueryClient();
    render(
      <QC>
        <EvaluationStatus
          job={filterJob}
          liveViolations={{ security: [{ severity: 'major', principle: 'P1', file: 'a.py', line: 1 }] }}
        />
      </QC>
    );
    expect(screen.queryByText(/carried forward hidden/)).not.toBeInTheDocument();
  });
});
