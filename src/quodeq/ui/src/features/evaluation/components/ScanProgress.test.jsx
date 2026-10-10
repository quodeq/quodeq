import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvalLogContext } from '../eval-log/EvalLogContext.js';
import ScanProgress from './ScanProgress.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { getEvaluationProgress } from '../../../api/index.js';

vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn(() => Promise.resolve({ dimensions: [], totalElapsedS: 0 })),
}));

function withEvalLog(ui, ctx) {
  const QC = withQueryClient();
  return render(
    <QC>
      <EvalLogContext.Provider value={ctx}>{ui}</EvalLogContext.Provider>
    </QC>,
  );
}

const baseJob = { jobId: 'job-1', status: 'running', logs: [] };

describe('ScanProgress terminal button', () => {
  beforeEach(() => { localStorage.clear(); });

  it('clicking the terminal button calls openLog with the jobId', () => {
    const openLog = vi.fn();
    const closeLog = vi.fn();
    const updateJobStatus = vi.fn();
    withEvalLog(<ScanProgress job={baseJob} />, {
      activeJobId: null, status: 'idle', openLog, closeLog, updateJobStatus,
    });
    const btn = screen.getByLabelText('Show console');
    fireEvent.click(btn);
    expect(openLog).toHaveBeenCalledWith('job-1', null, 'running');
    expect(closeLog).not.toHaveBeenCalled();
  });

  it('clicking again when log already shows this job calls closeLog', () => {
    const openLog = vi.fn();
    const closeLog = vi.fn();
    const updateJobStatus = vi.fn();
    withEvalLog(<ScanProgress job={baseJob} />, {
      activeJobId: 'job-1', status: 'streaming', openLog, closeLog, updateJobStatus,
    });
    const btn = screen.getByLabelText('Hide console');
    fireEvent.click(btn);
    expect(closeLog).toHaveBeenCalled();
    expect(openLog).not.toHaveBeenCalled();
  });

  it('button reflects "open" only when activeJobId matches this jobId', () => {
    const openLog = vi.fn();
    const closeLog = vi.fn();
    const updateJobStatus = vi.fn();
    withEvalLog(<ScanProgress job={baseJob} />, {
      activeJobId: 'other-job', status: 'streaming', openLog, closeLog, updateJobStatus,
    });
    expect(screen.queryByLabelText('Hide console')).toBeNull();
    expect(screen.getByLabelText('Show console')).toBeInTheDocument();
  });

  it('does not render the inline ConsoleLogViewer anymore', () => {
    withEvalLog(<ScanProgress job={baseJob} />, {
      activeJobId: 'job-1', status: 'streaming', openLog: vi.fn(), closeLog: vi.fn(), updateJobStatus: vi.fn(),
    });
    expect(document.querySelector('.console-shell')).toBeNull();
  });
});

describe('ScanProgress partial coverage signal', () => {
  function payload(dim) {
    return {
      runId: 'r1', phase: 'analyzing', currentDimension: null,
      totalElapsedS: 60, projectFiles: 100, state: 'running',
      dimensions: [dim],
    };
  }

  const ctx = { openLog: vi.fn(), closeLog: vi.fn(), updateJobStatus: vi.fn() };

  it('renders coverage % in amber when dim.exitReason is a non-done value', async () => {
    getEvaluationProgress.mockResolvedValueOnce(payload({
      id: 'maintainability', state: 'done',
      files: { taken: 8, total: 100 },
      violations: 74, compliance: 9,
      elapsedS: 754, exitReason: 'time_limit',
    }));
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    // Wait for react-query to settle, then open the per-dim detail panel.
    fireEvent.click(await screen.findByTitle('Show per-dimension detail'));
    await screen.findByText('maintainability');
    const pctEl = container.querySelector('.scan-progress__coverage--partial');
    expect(pctEl).not.toBeNull();
    expect(pctEl.textContent).toMatch(/8\s*%/);
  });

  it('renders coverage % in default colour when exitReason is "done"', async () => {
    getEvaluationProgress.mockResolvedValueOnce(payload({
      id: 'maintainability', state: 'done',
      files: { taken: 100, total: 100 },
      violations: 0, compliance: 5,
      elapsedS: 60, exitReason: 'done',
    }));
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    fireEvent.click(await screen.findByTitle('Show per-dimension detail'));
    await screen.findByText('maintainability');
    expect(container.querySelector('.scan-progress__coverage--partial')).toBeNull();
  });

  it('clamps coverage % to 100 in a done dim when taken exceeds total (count drift)', async () => {
    // Regression for the clamp-adoption change: the old inline
    // Math.round((taken/total)*100) had no cap and would have printed 105%.
    getEvaluationProgress.mockResolvedValueOnce(payload({
      id: 'maintainability', state: 'done',
      files: { taken: 105, total: 100 },
      violations: 0, compliance: 5,
      elapsedS: 60, exitReason: 'done',
    }));
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    fireEvent.click(await screen.findByTitle('Show per-dimension detail'));
    await screen.findByText('maintainability');
    const pctEl = container.querySelector('.scan-progress__coverage');
    expect(pctEl.textContent).toMatch(/^100\s*%$/);
  });
});

// The coverage block and the footer budget line left the run screen (the
// bar shows this run only; the run's figures are in details), so only the
// per-dimension rows are pinned here.
describe('ScanProgress details rows', () => {
  const ctx = { activeJobId: null, status: 'idle', openLog: vi.fn(), closeLog: vi.fn(), updateJobStatus: vi.fn() };

  function coveragePayload() {
    return {
      runId: 'r1', phase: 'analyzing', currentDimension: 'security',
      totalElapsedS: 60, projectFiles: 100, state: 'running',
      dimensions: [
        { id: 'security', state: 'running', files: { taken: 8, total: 20 },
          filesCached: 80, filesProjectTotal: 100 },
      ],
    };
  }

  it('never shows a per-dimension budget in the detail rows', async () => {
    const payload = coveragePayload();
    payload.budgetS = 600;
    // Legacy payloads carried the run budget on the running dim; it must
    // not render as if the dimension had its own allowance.
    payload.dimensions[0].budgetS = 600;
    payload.dimensions[0].elapsedS = 78;
    getEvaluationProgress.mockResolvedValue(payload);
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    fireEvent.click(await screen.findByTitle('Show per-dimension detail'));
    const row = (await screen.findByText('security')).closest('.scan-progress__dim');
    expect(row.textContent).toContain('1m 18s');
    expect(row.textContent).not.toContain('budget');
  });
});
