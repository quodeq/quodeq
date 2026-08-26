import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DashboardPage from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';
import { preloadRunHistoryPanel } from './AccumulatedOverviewPanel.jsx';

vi.mock('./AccumulatedOverviewPanel.jsx', async (importOriginal) => {
  const mod = await importOriginal();
  return { ...mod, preloadRunHistoryPanel: vi.fn() };
});

// The score-history chart is a separate lazy chunk: without warming it
// while the boot loader/skeleton is still up, the freshly mounted overview
// shows the chart placeholder for a beat — the exact placeholder flash the
// startup hold exists to remove.
describe('DashboardPage warms the score-history chunk', () => {
  it('kicks the preload on mount, while still loading', () => {
    render(
      <SidePaneProvider>
        <DashboardPage
          data={{
            projectsLoaded: true,
            projects: [{ id: 'p1', name: 'p1' }],
            selectedProject: 'p1',
            selectedSource: 'local',
            dashboard: null,
            accumulated: null,
            loading: true,
            isFetching: true,
            error: null,
            availableRuns: [],
          }}
          callbacks={{}}
          runMode={false}
        />
      </SidePaneProvider>,
    );
    expect(preloadRunHistoryPanel).toHaveBeenCalled();
  });
});
