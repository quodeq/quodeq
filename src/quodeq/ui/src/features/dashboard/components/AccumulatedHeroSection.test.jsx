import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { AccumulatedHeroSection } from './AccumulatedHeroSection.jsx';

// The line under the Overview title: the project's size first, then its
// top languages, so how big the codebase is reads at a glance.
describe('AccumulatedHeroSection sub-line', () => {
  const accumulated = { summary: { violations: 0, compliance: 0, severity: {} } };

  it('leads with the total file count, then the languages', () => {
    render(<AccumulatedHeroSection accumulated={accumulated} projectInfo={{ filesCount: 3925, languageStats: { py: 2329, jsx: 866 } }} />);
    expect(screen.getByText('3,925 files · 2329 python 866 jsx')).toBeInTheDocument();
  });

  it('shows the total alone when there are no language stats', () => {
    render(<AccumulatedHeroSection accumulated={accumulated} projectInfo={{ filesCount: 61 }} />);
    expect(screen.getByText('61 files')).toBeInTheDocument();
  });

  it('keeps the language line as it was when the count is unknown', () => {
    render(<AccumulatedHeroSection accumulated={accumulated} projectInfo={{ languageStats: { py: 12 } }} />);
    expect(screen.getByText('12 python')).toBeInTheDocument();
  });
});
