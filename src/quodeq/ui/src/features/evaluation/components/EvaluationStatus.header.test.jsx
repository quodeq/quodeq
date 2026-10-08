import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import EvaluationStatus from './EvaluationStatus.jsx';

// The header and identity strip only; the strip, progress and feed have
// their own tests.
vi.mock('./ScanProgress.jsx', () => ({ default: () => null }));
vi.mock('./JobStatStrip.jsx', () => ({ default: () => null }));
vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn().mockResolvedValue({ dimensions: [] }),
}));

function renderWithClient(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const baseJob = { jobId: 'job-1', status: 'running', source: 'internal', logs: [], dimensions: [] };

describe('the run header', () => {
  it('a running job shows the status dot and a stop pill, not the RUNNING pill', () => {
    const onCancel = vi.fn();
    renderWithClient(<EvaluationStatus job={baseJob} onCancel={onCancel} />);
    expect(screen.getByLabelText('running')).toHaveClass('eval-run-dot');
    expect(document.querySelector('.eval-run-pill')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('terminal states keep their pill and buttons', () => {
    renderWithClient(<EvaluationStatus job={{ ...baseJob, status: 'done' }} onDismiss={vi.fn()} />);
    expect(document.querySelector('.eval-run-pill--done')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /stop/i })).toBeNull();
    expect(screen.getByRole('button', { name: /view results/i })).toBeInTheDocument();
  });

  it('the identity strip has no job id and the repository cell opens Repositories', () => {
    const onGoToProjects = vi.fn();
    renderWithClient(<EvaluationStatus job={{ ...baseJob, jobId: 'job-123' }} jobProjectInfo={{ name: 'quodeq' }} onGoToProjects={onGoToProjects} />);
    expect(document.querySelector('.eval-identity').textContent).not.toMatch('job-123');
    fireEvent.click(screen.getByRole('button', { name: 'quodeq' }));
    expect(onGoToProjects).toHaveBeenCalledTimes(1);
  });

  it('an unknown repository stays a plain dash', () => {
    renderWithClient(<EvaluationStatus job={baseJob} onGoToProjects={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '—' })).toBeNull();
  });
});
