import { describe, it, expect, vi } from 'vitest';
import { historyRoute } from './historyRoute.jsx';

function routeProps(overrides = {}) {
  return {
    dashboardData: { dashboard: { trend: [], partialRuns: [] }, accumulated: null, availableRuns: [], loading: false, isFetching: false, error: null },
    navigation: {
      historySelectedRun: null, projects: [], projectsLoaded: true, selectedProject: 'proj1', selectedSource: 'local',
      handleNavigate: vi.fn(), setHistorySelectedRun: vi.fn(),
    },
    handleRunDeleted: vi.fn(),
    ...overrides,
  };
}

describe('historyRoute', () => {
  it('passes handleRunDeleted as the History onRunDeleted callback', () => {
    const props = routeProps();
    const el = historyRoute({}, props);
    expect(el.props.callbacks.onRunDeleted).toBe(props.handleRunDeleted);
  });
});
