import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
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
    expect(document.querySelector('.vlive-dimension-name')).toHaveTextContent('reliability');
    expect(document.querySelector('.vlive-dimension-count')).toHaveTextContent('2');
    expect(screen.getByText('2 across 1 dimension')).toBeInTheDocument();
    expect(screen.getByText('1 crit')).toBeInTheDocument();
    expect(screen.getByText('1 maj')).toBeInTheDocument();
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
    fireEvent.click(document.querySelector('.vlive-dimension-label'));
    const row = screen.getByRole('button', { name: /^critical finding: Crash on nil/i });
    expect(row).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
  });

  describe('dimension groups', () => {
    const twoDims = {
      security: [{ severity: 'major', principle: 'input validation', file: 'S.swift', line: 1 }],
      reliability: [{ severity: 'critical', principle: 'fault tolerance', file: 'A.swift', line: 56 }],
    };
    const group = (name) => Array.from(document.querySelectorAll('.vlive-dimension-label'))
      .find((b) => b.querySelector('.vlive-dimension-name')?.textContent === name);
    const groupNames = () => Array.from(document.querySelectorAll('.vlive-dimension-name')).map((n) => n.textContent);

    // Opening the running group on its own mounted every one of its rows,
    // and a dimension with thousands of findings made the screen lag.
    it('all start closed while a run is on, the one being analyzed on top', async () => {
      getEvaluationProgress.mockResolvedValue({ currentDimension: 'reliability', dimensions: [{ id: 'reliability', state: 'running' }] });
      renderFeed({ liveViolations: twoDims, job: { jobId: 'j3', status: 'running' } });
      await waitFor(() => expect(groupNames()).toEqual(['reliability', 'security']));
      expect(group('reliability')).toHaveAttribute('aria-expanded', 'false');
      expect(group('security')).toHaveAttribute('aria-expanded', 'false');
      expect(group('reliability')).toHaveTextContent('scanning');
    });

    it('all start closed once the run is over', () => {
      renderFeed({ liveViolations: twoDims, job: { jobId: 'j5', status: 'done' } });
      expect(group('reliability')).toHaveAttribute('aria-expanded', 'false');
      expect(group('security')).toHaveAttribute('aria-expanded', 'false');
    });

    it('opens several at once', () => {
      renderFeed({ liveViolations: twoDims });
      fireEvent.click(group('reliability'));
      fireEvent.click(group('security'));
      expect(group('reliability')).toHaveAttribute('aria-expanded', 'true');
      expect(group('security')).toHaveAttribute('aria-expanded', 'true');
    });

    const many = { security: Array.from({ length: 120 }, (_, i) => ({ severity: 'minor', principle: 'p', file: `F${i}.swift`, line: i })) };
    const groupRows = () => document.querySelectorAll('.vlive-dimension-group .vdetail-row').length;

    it('lists every finding of an open group when there is no scroller to virtualize against', () => {
      renderFeed({ liveViolations: many });
      fireEvent.click(group('security'));
      expect(screen.getByRole('list', { name: 'security findings' })).toBeInTheDocument();
      expect(groupRows()).toBe(120);
    });

    // A dimension can hold thousands of findings; mounting all of them is
    // what made long runs lag. Under the dashboard scroller only the rows
    // near the viewport mount, like the Explorer's detail pages.
    it('mounts only the rows near the viewport inside the dashboard scroller', () => {
      const column = document.createElement('div');
      column.className = 'app-shell__main-column';
      const scroller = document.createElement('main');
      scroller.className = 'dashboard';
      // jsdom has no layout; the virtualizer reads the viewport off these.
      Object.defineProperty(scroller, 'offsetHeight', { value: 400 });
      Object.defineProperty(scroller, 'offsetWidth', { value: 800 });
      column.appendChild(scroller);
      document.body.appendChild(column);
      // The virtualizer measures each mounted row's offsetHeight.
      const rowHeight = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(39);
      try {
        const QC = withQueryClient();
        render(<QC><LiveViolationsFeed liveViolations={many} /></QC>, { container: scroller });
        fireEvent.click(group('security'));
        expect(groupRows()).toBeGreaterThan(0);
        // A 400px viewport of 39px rows plus the overscan, nowhere near 120.
        expect(groupRows()).toBeLessThan(30);
      } finally {
        rowHeight.mockRestore();
        column.remove();
      }
    });

    it('keeps a row open when a new finding lands in its group', () => {
      const one = { security: [{ severity: 'major', principle: 'p', file: 'A.swift', line: 1, title: 'First' }] };
      const QC = withQueryClient();
      const { rerender } = render(<QC><LiveViolationsFeed liveViolations={one} /></QC>);
      fireEvent.click(group('security'));
      const inGroup = () => within(document.querySelector('.vlive-dimension-group'));
      fireEvent.click(inGroup().getByRole('button', { name: /finding: First/i }));
      const two = { security: [...one.security, { severity: 'critical', principle: 'p', file: 'B.swift', line: 2, title: 'Second' }] };
      rerender(<QC><LiveViolationsFeed liveViolations={two} /></QC>);
      expect(inGroup().getByRole('button', { name: /finding: First/i })).toHaveAttribute('aria-expanded', 'true');
      expect(inGroup().getByRole('button', { name: /finding: Second/i })).toHaveAttribute('aria-expanded', 'false');
    });
  });

  it('shows the passing checks next to the violations while running', async () => {
    // The console line prints "40 v · 1056 c"; the header says the same
    // thing in words, so the feed never reads as "the run found 40 things".
    getEvaluationProgress.mockResolvedValue({
      currentDimension: 'reliability',
      dimensions: [
        { id: 'reliability', state: 'running', files: { taken: 30, total: 100 }, compliance: 1056 },
        { id: 'security', state: 'done', files: { taken: 10, total: 10 }, compliance: 200 },
      ],
    });
    renderFeed({ liveViolations: violations, job: { jobId: 'j1', status: 'running' } });
    expect(await screen.findByText(/1256 checks passed/)).toBeInTheDocument();
  });

  it('keeps the passing checks on a finished job', async () => {
    getEvaluationProgress.mockResolvedValue({
      dimensions: [{ id: 'reliability', state: 'done', files: { taken: 1, total: 1 }, compliance: 1 }],
    });
    renderFeed({ liveViolations: violations, job: { jobId: 'j3', status: 'done' } });
    expect(await screen.findByText(/1 check passed/)).toBeInTheDocument();
  });

  it('counts only what it renders', () => {
    renderFeed({ liveViolations: violations, hiddenCarriedCount: 5 });
    expect(screen.getByText('2 across 1 dimension')).toBeInTheDocument();
  });

  it('keeps the header when the filter empties the list', () => {
    // A fully-cached dimension produces zero new findings. Returning null
    // here would make the feed vanish and read as "nothing found". The
    // "0 across 0 dimensions" phrasing would be confusing, so a wholly
    // filtered-out run says "no new findings" instead.
    renderFeed({ liveViolations: {}, hiddenCarriedCount: 12 });
    expect(screen.getByText(/no new findings/)).toBeInTheDocument();
    expect(screen.getByText(/12 carried forward hidden/)).toBeInTheDocument();
    expect(screen.queryByText(/across 0 dimension/)).toBeNull();
  });

  it('still renders nothing when there is genuinely nothing', () => {
    const { container } = renderFeed({ liveViolations: {}, hiddenCarriedCount: 0 });
    expect(container.firstChild).toBeNull();
  });

  it('omits the bordered card when the filter emptied a terminal job, keeping only the disclosure', () => {
    const { container } = renderFeed({
      job: { jobId: 'j1', status: 'done' },
      liveViolations: {},
      hiddenCarriedCount: 12,
    });
    expect(screen.getByText(/12 carried forward hidden/)).toBeInTheDocument();
    expect(container.querySelector('.vlive-card')).toBeNull();
  });
});
