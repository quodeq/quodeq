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
  suppressed: 0,
};

const dashboard = { selectedRun: { runId: 'r1', dateLabel: '4 Jul 2026' } };

describe('RunHeroSection suppressed note', () => {
  it('shows how many findings the suppression filters hid', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={{ ...baseSummary, suppressed: 404 }}
      />,
    );
    expect(screen.getByText(/404 suppressed/)).toBeTruthy();
  });

  it('renders no note when nothing was suppressed', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={baseSummary}
      />,
    );
    expect(screen.queryByText(/suppressed/)).toBeNull();
  });

  it('shows the note even when every violation was suppressed', () => {
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={{
          ...baseSummary,
          totalViolations: 0,
          severity: { critical: 0, major: 0, minor: 0 },
          suppressed: 535,
        }}
      />,
    );
    expect(screen.getByText(/535 suppressed/)).toBeTruthy();
  });

  it('counts deletions, which the dismissed-only number misses', () => {
    // The case that motivated this: a project whose triage history is all
    // deletions reads dismissed: 0 while 391 findings are hidden from the view.
    render(
      <RunHeroSection
        dashboard={dashboard}
        selectedRunId="r1"
        runSummary={{ ...baseSummary, dismissed: 0, suppressed: 391 }}
      />,
    );
    expect(screen.getByText(/391 suppressed/)).toBeTruthy();
  });
});
