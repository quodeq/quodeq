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
});

describe('ScanProgress total coverage (incremental runs)', () => {
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

  it('shows total coverage plus this-run detail when a cached portion exists', async () => {
    getEvaluationProgress.mockResolvedValue(coveragePayload());
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    // 80 cached + 8 taken = 88 of 100 → 88% total; this run 8 / 20.
    expect(await screen.findByText('88 / 100')).toBeInTheDocument();
    expect(screen.getByText(/88% total/)).toBeInTheDocument();
    expect(screen.getByText(/this run 8 \/ 20/)).toBeInTheDocument();
  });

  it('renders a dim cached segment and a bright run segment', async () => {
    getEvaluationProgress.mockResolvedValue(coveragePayload());
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    await screen.findByText('88 / 100');
    const cached = container.querySelector('.scan-progress__bar-fill--cached');
    expect(cached).not.toBeNull();
    expect(cached.style.width).toBe('80%');
    const fills = container.querySelectorAll('.scan-progress__bar-wrap .scan-progress__bar-fill:not(.scan-progress__bar-fill--cached)');
    expect(fills[0].style.width).toBe('8%');
    expect(container.querySelector('.scan-progress__bar-wrap .scan-progress__bar'))
      .toHaveAttribute('title', '80 files analyzed in previous runs');
  });

  it('collapses to the run-only display when there is no cached portion', async () => {
    getEvaluationProgress.mockResolvedValue({
      runId: 'r1', phase: 'analyzing', currentDimension: 'security',
      totalElapsedS: 60, projectFiles: 60, state: 'running',
      dimensions: [
        { id: 'security', state: 'running', files: { taken: 12, total: 60 },
          filesCached: 0, filesProjectTotal: 60 },
      ],
    });
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('12 / 60')).toBeInTheDocument();
    expect(screen.getByText(/checks · 20%/)).toBeInTheDocument();
    expect(screen.queryByText(/this run/)).toBeNull();
    expect(container.querySelector('.scan-progress__bar-fill--cached')).toBeNull();
    expect(container.querySelector('.scan-progress__bar-wrap .scan-progress__bar'))
      .not.toHaveAttribute('title');
  });

  it('collapses to the run-only display on legacy payloads without coverage fields', async () => {
    getEvaluationProgress.mockResolvedValue({
      runId: 'r1', phase: 'analyzing', currentDimension: 'security',
      totalElapsedS: 60, projectFiles: 60, state: 'running',
      dimensions: [
        { id: 'security', state: 'running', files: { taken: 12, total: 60 } },
      ],
    });
    const { container } = withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('12 / 60')).toBeInTheDocument();
    expect(container.querySelector('.scan-progress__bar-fill--cached')).toBeNull();
  });

  it('appends the excluded count to the coverage line when files were excluded', async () => {
    const payload = coveragePayload();
    payload.dimensions[0].filesExcluded = 3;
    getEvaluationProgress.mockResolvedValue(payload);
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('88 / 100')).toBeInTheDocument();
    expect(screen.getByText(/3 excluded \(size cap\)/)).toBeInTheDocument();
  });

  it('shows no excluded segment when the payload reports zero excluded', async () => {
    const payload = coveragePayload();
    payload.dimensions[0].filesExcluded = 0;
    getEvaluationProgress.mockResolvedValue(payload);
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('88 / 100')).toBeInTheDocument();
    expect(screen.queryByText(/excluded/)).toBeNull();
  });

  it('shows no excluded segment on legacy payloads without the field', async () => {
    getEvaluationProgress.mockResolvedValue(coveragePayload());
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('88 / 100')).toBeInTheDocument();
    expect(screen.queryByText(/excluded/)).toBeNull();
  });

  it('fully-cached re-scan shows coverage, not preparing', async () => {
    // Nothing new to analyze this run: totalFiles 0 but full coverage data.
    getEvaluationProgress.mockResolvedValue({
      runId: 'r1', phase: 'analyzing', currentDimension: null,
      totalElapsedS: 5, projectFiles: 100, state: 'running',
      dimensions: [
        { id: 'security', state: 'done', files: { taken: 0, total: 0 },
          filesCached: 100, filesProjectTotal: 100 },
      ],
    });
    withEvalLog(<ScanProgress job={baseJob} />, ctx);
    expect(await screen.findByText('100 / 100')).toBeInTheDocument();
    expect(screen.getByText(/100% total/)).toBeInTheDocument();
    expect(screen.getByText(/nothing new this run/)).toBeInTheDocument();
    expect(screen.queryByText(/this run 0 \/ 0/)).toBeNull();
    expect(screen.queryByText('preparing…')).toBeNull();
  });
});
