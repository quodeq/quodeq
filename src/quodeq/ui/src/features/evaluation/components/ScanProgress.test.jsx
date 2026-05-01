import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvalLogContext } from '../eval-log/EvalLogContext.js';
import ScanProgress from './ScanProgress.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

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
