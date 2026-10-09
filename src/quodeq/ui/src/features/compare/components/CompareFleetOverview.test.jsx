import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompareFleetKpis from './CompareFleetKpis.jsx';
import CompareFleetMatrix from './CompareFleetMatrix.jsx';
import CompareDirectionMap from './CompareDirectionMap.jsx';
import CompareAttentionList from './CompareAttentionList.jsx';
import CompareDimensionHealth from './CompareDimensionHealth.jsx';
import { REASON_TYPE } from '../compareBoard.js';

const dim = (key, score, extra = {}) => ({ key, label: key, name: key, score, fromRunId: 'r1', fromDateLabel: '1 Oct', ...extra });
const row = (over) => ({
  id: over.name, name: over.name, score: 7, delta: null, totalFiles: 100, analyzedFiles: null,
  totalViolations: 20, totalCompliance: 80, severity: { critical: 1 }, lastISO: '2026-10-01T00:00:00Z',
  stale: false, remote: false, source: 'local', dims: [], ...over,
});
const ROWS = [
  row({ name: 'alpha', score: 8.5, delta: 0.6, totalFiles: 900, dims: [dim('security', 9), dim('usability', 8)] }),
  row({ name: 'beta', score: 6.5, delta: -0.4, stale: true, dims: [dim('security', 5), dim('usability', 8.5)] }),
  row({ name: 'gamma', score: 7.5, delta: null, dims: [dim('security', 7)] }),
];
const BOARD = [
  { key: 'security', label: 'security', avg: 7, delta: 0.1, violations: 30, perProject: ROWS.map((r) => ({ id: r.id, name: r.name, score: r.dims[0].score })) },
  { key: 'usability', label: 'usability', avg: 8.25, delta: null, violations: 5, perProject: ROWS.slice(0, 2).map((r) => ({ id: r.id, name: r.name, score: r.dims[1].score })) },
];
const FLEET = { score: 7.5, delta: 0.2, spread: 2, lead: ROWS[0], trail: ROWS[1] };

describe('CompareFleetKpis', () => {
  it('states size-normalised exposure and freshness', () => {
    render(<CompareFleetKpis rows={ROWS} fleet={FLEET} />);
    const strip = screen.getByRole('region', { name: 'Fleet summary' });
    expect(strip).toHaveTextContent(/1,100\s*files in 3 projects/);
    expect(strip).toHaveTextContent('per 100 analysed files');
    expect(strip).toHaveTextContent('2/3');
    expect(strip).toHaveTextContent('1 graded on stale code');
  });
});

describe('CompareFleetMatrix', () => {
  const renderMatrix = (props = {}) => render(
    <CompareFleetMatrix rows={ROWS} board={BOARD} fleetScore={7.5} onOpenProject={vi.fn()} onOpenProjectDimension={vi.fn()} {...props} />,
  );

  it('outlines only the best (solid) and worst (dashed) of each dimension', () => {
    const { container } = renderMatrix();
    expect(container.querySelectorAll('.compare-heat__tile--best')).toHaveLength(2);
    expect(container.querySelectorAll('.compare-heat__tile--worst')).toHaveLength(2);
    expect(within(container).getByText('9.0')).toHaveClass('compare-heat__tile--best');
    expect(within(container).getByText('5.0')).toHaveClass('compare-heat__tile--worst');
  });

  it('a tile opens that project’s own dimension', async () => {
    const onOpenProjectDimension = vi.fn();
    renderMatrix({ onOpenProjectDimension });
    await userEvent.click(screen.getByTitle('open security in beta'));
    expect(onOpenProjectDimension).toHaveBeenCalledWith({ id: 'beta', source: 'local', runId: 'r1', dimName: 'security', dateLabel: '1 Oct' });
  });

  it('a header ranks by its dimension; again reverses; unscored projects stay last', async () => {
    renderMatrix();
    const names = () => screen.getAllByRole('rowheader').map((h) => h.textContent).filter((tx) => /alpha|beta|gamma/.test(tx));
    await userEvent.click(screen.getByRole('button', { name: 'Rank by usability' }));
    expect(names()[0]).toMatch(/beta/);
    await userEvent.click(screen.getByRole('button', { name: 'Rank by usability' }));
    expect(names().map((n) => n.replace(/^\d+/, ''))).toEqual(['alpha', 'beta', 'gamma']);
  });

  it('the footer gives each dimension’s fleet average and how many projects were scored', () => {
    renderMatrix();
    expect(screen.getByText('2 of 3')).toBeInTheDocument();
    expect(screen.getByText('3 of 3')).toBeInTheDocument();
  });
});

describe('CompareDirectionMap', () => {
  it('plots every project, the ones with no runs in 30 days hollow', () => {
    const { container } = render(<CompareDirectionMap rows={ROWS} fleetScore={7.5} hover={null} setHover={vi.fn()} onOpenProject={vi.fn()} />);
    expect(screen.getByRole('img', { name: /Direction map/ })).toBeInTheDocument();
    expect(container.querySelectorAll('.compare-dirmap__pt')).toHaveLength(3);
    expect(container.querySelectorAll('.compare-dirmap__pt.is-still')).toHaveLength(1);
    expect(container.querySelector('.compare-dirmap__pt.is-still')).toHaveTextContent('gamma');
    expect(container.querySelector('.compare-dirmap__stale')).toHaveTextContent('stale');
  });
});

describe('CompareAttentionList', () => {
  it('turns reasons into tags and opens that project\'s own weakest dimension', async () => {
    const onOpenProjectDimension = vi.fn();
    const items = [{ row: ROWS[1], level: 'severe', worstDim: 'security', reasons: [
      { type: REASON_TYPE.WORST_DIM, dim: 'security', score: 5 },
      { type: REASON_TYPE.STALE, commits: 12 },
    ] }];
    render(<CompareAttentionList items={items} hover={null} setHover={vi.fn()} onOpenProject={vi.fn()} onOpenProjectDimension={onOpenProjectDimension} />);
    expect(screen.getByText('security at 5.0')).toBeInTheDocument();
    expect(screen.getByText('12 commits behind')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /open security/ }));
    expect(onOpenProjectDimension).toHaveBeenCalledWith({ id: 'beta', source: 'local', runId: 'r1', dimName: 'security', dateLabel: '1 Oct' });
  });

  it('opens a remote project itself, its dimension page being out of reach', async () => {
    const onOpenProject = vi.fn();
    const onOpenProjectDimension = vi.fn();
    const items = [{ row: { ...ROWS[1], remote: true }, level: 'severe', worstDim: 'security', reasons: [] }];
    render(<CompareAttentionList items={items} hover={null} setHover={vi.fn()} onOpenProject={onOpenProject} onOpenProjectDimension={onOpenProjectDimension} />);
    await userEvent.click(screen.getByRole('button', { name: /open security/ }));
    expect(onOpenProject).toHaveBeenCalledWith('beta');
    expect(onOpenProjectDimension).not.toHaveBeenCalled();
  });
});

describe('CompareDimensionHealth', () => {
  it('ranks weakest first with the grade mix, below-good count and weakest project', async () => {
    const openDimension = vi.fn();
    render(<CompareDimensionHealth board={BOARD} openDimension={openDimension} />);
    const rows = screen.getAllByRole('button', { name: /security|usability/ });
    expect(rows[0]).toHaveTextContent(/^security/);
    expect(rows[0]).toHaveTextContent('1 of 3');
    expect(rows[0]).toHaveTextContent(/beta\s*5\.0/);
    await userEvent.click(rows[0]);
    expect(openDimension).toHaveBeenCalledWith('security');
  });
});
