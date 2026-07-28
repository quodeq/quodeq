import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import LiveViolationsFeed from './LiveViolationsFeed.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

vi.mock('../../../api/index.js', () => ({
  getEvaluationProgress: vi.fn(),
}));
import { getEvaluationProgress } from '../../../api/index.js';

function renderFeed(props) {
  const QC = withQueryClient();
  return render(<QC><LiveViolationsFeed {...props} /></QC>);
}

const violations = {
  reliability: [
    { severity: 'critical', principle: 'fault tolerance', file: 'A.swift', line: 56, title: 'Crash on nil' },
    { severity: 'major', principle: 'fault tolerance', file: 'B.swift', line: 12 },
  ],
};

describe('LiveViolationsFeed', () => {
  beforeEach(() => { getEvaluationProgress.mockReset(); });

  it('renders nothing without violations', () => {
    const { container } = renderFeed({ liveViolations: {} });
    expect(container.firstChild).toBeNull();
  });

  it('groups violations per dimension with counts', () => {
    renderFeed({ liveViolations: violations });
    expect(screen.getByText('reliability')).toBeInTheDocument();
    expect(screen.getByText('2 across 1 dimension')).toBeInTheDocument();
    expect(screen.getByText('critical')).toBeInTheDocument();
    expect(screen.getByText('major')).toBeInTheDocument();
  });

  it('streams the queued count from progress while running', async () => {
    getEvaluationProgress.mockResolvedValue({
      currentDimension: 'reliability',
      dimensions: [
        { id: 'reliability', state: 'running', files: { taken: 30, total: 1407 } },
      ],
    });
    renderFeed({ liveViolations: violations, job: { jobId: 'j1', status: 'running' } });
    expect(await screen.findByText(/scanning for more · 1377 files queued/)).toBeInTheDocument();
    expect(screen.getByText(/· streaming/)).toBeInTheDocument();
  });

  it('shows no streaming footer once the job is terminal', () => {
    renderFeed({ liveViolations: violations, job: { jobId: 'j2', status: 'done' } });
    expect(screen.queryByText(/scanning for more/)).toBeNull();
    expect(screen.queryByText(/streaming/)).toBeNull();
  });

  it('expands a row to its detail on click', () => {
    renderFeed({ liveViolations: violations });
    const row = screen.getByRole('button', { name: /critical finding: Crash on nil/i });
    expect(row).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
  });

  it('counts only what it renders', () => {
    renderFeed({ liveViolations: violations, hiddenCarriedCount: 5 });
    expect(screen.getByText('2 across 1 dimension')).toBeInTheDocument();
  });

  it('keeps the header when the filter empties the list', () => {
    // A fully-cached dimension produces zero new findings. Returning null
    // here would make the feed vanish and read as "nothing found".
    renderFeed({ liveViolations: {}, hiddenCarriedCount: 12 });
    expect(screen.getByText(/12 carried forward hidden/)).toBeInTheDocument();
  });

  it('still renders nothing when there is genuinely nothing', () => {
    const { container } = renderFeed({ liveViolations: {}, hiddenCarriedCount: 0 });
    expect(container.firstChild).toBeNull();
  });
});
