import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Suspense } from 'react';
import '@testing-library/jest-dom/vitest';
import { MainContent } from './renderers.jsx';

// The empty-projects wall's "add a project" opens the analyze screen through
// the navigation bundle's onStartAnalyze.
describe('MainContent empty-projects wall', () => {
  beforeEach(() => localStorage.clear());

  it('add a project calls onStartAnalyze', () => {
    const onStartAnalyze = vi.fn();
    const props = {
      navigation: {
        projects: [], selectedSource: 'local', projectsLoaded: true, isEvaluating: false,
        onStartAnalyze, onTakeTour: vi.fn(),
      },
    };
    render(
      <Suspense fallback={null}>
        <MainContent activePage={{ page: 'explorer' }} props={props} />
      </Suspense>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'add a project' }));
    expect(onStartAnalyze).toHaveBeenCalledTimes(1);
  });
});
