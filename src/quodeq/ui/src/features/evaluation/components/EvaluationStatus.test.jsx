import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';

vi.mock('./LiveViolationsFeed.jsx', () => ({ default: () => null }));
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
vi.mock('./JobStatStrip.jsx', () => ({ default: () => null }));
// The identity strip reads the shared progress query for its "mode" cell.
vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn().mockResolvedValue(null),
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
