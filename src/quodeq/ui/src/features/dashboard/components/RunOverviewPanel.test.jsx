import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { RunHeroSection } from './RunOverviewPanel.jsx';

const baseSummary = {
  overallGrade: 'Fair',
  numericAverage: '6.0',
  totalViolations: 131,
  totalCompliance: 175,
  dimensionCount: 1,
  severity: { critical: 0, major: 11, minor: 120 },
  dismissed: 0,
};

const dashboard = { selectedRun: { runId: 'r1', dateLabel: '4 Jul 2026' } };

describe('RunHeroSection dismissed note', () => {
  it('shows how many findings the dismissed filter hid', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={{ ...baseSummary, dismissed: 404 }}
      />,
    );
    expect(screen.getByText(/404 dismissed hidden/)).toBeTruthy();
  });

  it('renders no note when nothing was dismissed', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={baseSummary}
      />,
    );
    expect(screen.queryByText(/dismissed hidden/)).toBeNull();
  });

  it('shows the note even when every violation was dismissed', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={{
          ...baseSummary,
          totalViolations: 0,
          severity: { critical: 0, major: 0, minor: 0 },
          dismissed: 535,
        }}
      />,
    );
    expect(screen.getByText(/535 dismissed hidden/)).toBeTruthy();
  });
});
