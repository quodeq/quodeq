import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ScanProgressBar } from './ScanProgressParts.jsx';

describe('ScanProgressBar accessibility', () => {
  it('exposes the run-only bar as a labelled progressbar with the current percent', () => {
    render(
      <ScanProgressBar
        showCoverage={false}
        cachedFiles={0}
        cachedPctWidth={0}
        runPctWidth={0}
        overallPct={42}
        coveredPct={42}
        isRunning
        projectTotal={0}
        coveredFiles={0}
        takenFiles={42}
      />,
    );
    const bar = screen.getByRole('progressbar', { name: 'Scan progress' });
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).toHaveAttribute('aria-valuenow', '42');
  });

  it('uses the total repo coverage percent (not the this-run percent) once coverage is segmented', () => {
    render(
      <ScanProgressBar
        showCoverage
        cachedFiles={80}
        cachedPctWidth={80}
        runPctWidth={8}
        overallPct={40}
        coveredPct={88}
        isRunning
        projectTotal={100}
        coveredFiles={88}
        takenFiles={8}
      />,
    );
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '88');
  });
});
