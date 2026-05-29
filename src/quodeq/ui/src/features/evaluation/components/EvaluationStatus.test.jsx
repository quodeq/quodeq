import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';

vi.mock('./LiveViolationsFeed.jsx', () => ({ default: () => null }));
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
vi.mock('./JobStatStrip.jsx', () => ({ default: () => null }));

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

describe('JobIdLine', () => {
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
});
