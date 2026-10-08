import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ScanProgressBanner } from './ScanProgressParts.jsx';

describe('ScanProgressBanner on a finished run', () => {
  it('warns that the time budget ran out and the results are partial', () => {
    render(<ScanProgressBanner status="done" progress={{ exitReason: 'time_limit' }} logs={[]} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('time limit reached');
    expect(alert).toHaveTextContent(/partial/);
  });

  it('stays quiet on a clean finish', () => {
    render(<ScanProgressBanner status="done" progress={{ exitReason: null }} logs={[]} />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
