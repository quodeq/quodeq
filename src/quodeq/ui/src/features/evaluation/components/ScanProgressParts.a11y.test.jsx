import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ScanProgressBar } from './ScanProgressParts.jsx';

describe('ScanProgressBar accessibility', () => {
  it('exposes the run-only bar as a labelled progressbar with the current percent', () => {
    render(
      <ScanProgressBar overallPct={42} isRunning />,
    );
    const bar = screen.getByRole('progressbar', { name: 'Scan progress' });
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).toHaveAttribute('aria-valuenow', '42');
  });
});
