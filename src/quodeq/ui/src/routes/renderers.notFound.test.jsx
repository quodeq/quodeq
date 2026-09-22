import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Suspense } from 'react';
import { MainContent } from './renderers.jsx';

// An unrecognized route used to render nothing (a blank page, see the
// comment above MainContent's route dispatch). It must now log the
// unmatched route and render the existing not-found view instead of null.
describe('MainContent unrecognized route', () => {
  it('logs the unmatched route and renders the not-found empty state', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const props = {
      navigation: {
        projects: [{ id: 'p1' }],
        selectedSource: 'local',
        projectsLoaded: true,
      },
    };

    render(
      <Suspense fallback={null}>
        <MainContent activePage={{ page: 'not-a-real-route' }} props={props} />
      </Suspense>,
    );

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('[renderers]'),
      'not-a-real-route',
    );
    expect(screen.getByText('Page not found')).toBeInTheDocument();
  });
});
