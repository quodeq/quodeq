import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ExplorerStatsPanel from './ExplorerStatsPanel.jsx';

vi.mock('./DimensionScoreHistoryPanel.jsx', () => ({
  default: () => <div data-testid="history-panel" />,
}));

const baseProps = {
  overallScoreNum: 7.5,
  overallGrade: { grade: 'B' },
  allViolations: [{}, {}, {}],
  totalCompliant: 4,
  sev: { critical: 1, major: 2, minor: 0 },
  onSeverityBadge: () => () => {},
  onNavigate: null,
  onCardNavigate: () => {},
  trend: [],
  dimension: 'maintainability',
  activeRunId: 'run-1',
  granularity: 'run',
  onGranularityChange: () => {},
  onBarClick: () => {},
};

describe('ExplorerStatsPanel severity badges', () => {
  it('renders one badge per non-zero severity, most severe first', () => {
    render(<ExplorerStatsPanel {...baseProps} />);
    const badges = document.querySelectorAll('.principle-detail-sev-row .term-sev-badge');
    expect([...badges].map((b) => b.className)).toEqual([
      'term-sev-badge term-sev-badge--critical',
      'term-sev-badge term-sev-badge--major',
    ]);
    expect(badges[0]).toHaveTextContent('CRIT 1');
    expect(badges[1]).toHaveTextContent('MAJ 2');
  });

  it('drops the hint entirely when every severity is zero', () => {
    render(<ExplorerStatsPanel {...baseProps} sev={{ critical: 0, major: 0, minor: 0 }} />);
    expect(document.querySelector('.principle-detail-sev-row')).toBeNull();
  });

  it('wires each badge to its own severity when navigation is available', () => {
    const onSeverityBadge = vi.fn(() => () => {});
    render(
      <ExplorerStatsPanel
        {...baseProps}
        sev={{ critical: 1, major: 1, minor: 1 }}
        onNavigate={() => {}}
        onSeverityBadge={onSeverityBadge}
      />
    );
    expect(onSeverityBadge.mock.calls.map(([level]) => level)).toEqual(['critical', 'major', 'minor']);
    expect(screen.getByRole('button', { name: 'critical severity' })).toBeInTheDocument();
  });

  it('leaves badges unclickable when navigation is unavailable', () => {
    render(<ExplorerStatsPanel {...baseProps} />);
    expect(screen.queryByRole('button', { name: 'critical severity' })).toBeNull();
  });

  it('keeps the violations stat clickable with its aria label', () => {
    render(<ExplorerStatsPanel {...baseProps} onNavigate={() => {}} onCardNavigate={vi.fn()} />);
    const stat = screen.getByLabelText(/show all violations/i);
    expect(stat).toBeInTheDocument();
    fireEvent.click(stat);
  });
});
