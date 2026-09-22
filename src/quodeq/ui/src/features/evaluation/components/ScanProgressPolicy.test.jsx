import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvalLogContext } from '../eval-log/EvalLogContext.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { getEvaluationProgress } from '../../../api/index.js';
import ScanProgress from './ScanProgress.jsx';
import { ScanProgressBanner } from './ScanProgressParts.jsx';

vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn(),
}));

const policyProgress = {
  state: 'failed', exitReason: 'copilot_mcp_policy',
  dimensions: [], projectFiles: 211, totalElapsedS: 10,
};

function renderRun(job) {
  const QC = withQueryClient();
  return render(
    <QC>
      <EvalLogContext.Provider value={{ openLog: vi.fn(), closeLog: vi.fn(), updateJobStatus: vi.fn() }}>
        <ScanProgress job={job} />
      </EvalLogContext.Provider>
    </QC>,
  );
}

describe('Copilot policy error banner', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    getEvaluationProgress.mockResolvedValue(policyProgress);
  });

  it('shows the saved reason after reopening without any log text', async () => {
    const job = { jobId: 'job-1', status: 'failed', logs: [] };
    const first = renderRun(job);
    expect(await screen.findByText('Evaluation blocked by Copilot policy')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('administrator');
    expect(screen.getByRole('alert')).toHaveTextContent('findings');
    first.unmount();
    renderRun(job);
    expect(await screen.findByText('Evaluation blocked by Copilot policy')).toBeInTheDocument();
  });

  it('uses the saved job reason when progress cannot be loaded', async () => {
    getEvaluationProgress.mockRejectedValue(new Error('Progress unavailable'));
    renderRun({ jobId: 'job-1', status: 'failed', exitReason: 'copilot_mcp_policy', logs: [] });
    expect(await screen.findByRole('alert')).toHaveTextContent('Evaluation blocked by Copilot policy');
  });

  it('keeps completed results but warns that the evaluation stopped early', () => {
    render(<ScanProgressBanner status="done" progress={policyProgress} logs={[]} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Evaluation blocked by Copilot policy');
    expect(screen.getByRole('alert')).toHaveTextContent(/partial|incomplete/i);
  });

  it('does not label a user cancellation as a policy failure', () => {
    render(<ScanProgressBanner status="cancelled" progress={{ exitReason: 'cancelled' }} logs={[]} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
