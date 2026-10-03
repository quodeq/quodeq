import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import MapPage from './MapPage.jsx';

// Leaving the Map and coming back with the same scores payload must not
// rebuild the file tree: the tree is cached on the dimension objects, which
// react-query hands back unchanged.

vi.mock('../viz/core/fileTree.js', async (importOriginal) => {
  const mod = await importOriginal();
  return { ...mod, buildFileTree: vi.fn(mod.buildFileTree) };
});
import { buildFileTree } from '../viz/core/fileTree.js';

const DIMS = [{
  dimension: 'security',
  violations: [{ file: 'src/a.py', severity: 'major' }, { file: 'src/b.py', severity: 'minor' }],
  compliance: [{ file: 'src/a.py' }],
}];

function data(dimensions) {
  return {
    accumulated: { dimensions }, dashboard: null, projectName: 'p1',
    projects: [{ id: 'p1', name: 'p1' }], projectsLoaded: true,
    selectedProject: 'p1', selectedSource: 'local', loading: false, isFetching: false,
  };
}

const realBuilds = () => buildFileTree.mock.calls.filter(([dims]) => dims.length > 0).length;

describe('MapPage second visit', () => {
  it('builds the tree once across two visits with the same payload', () => {
    buildFileTree.mockClear();
    const first = render(<MapPage data={data(DIMS)} callbacks={{}} />);
    expect(first.container.querySelector('.map-viz-container')).toBeInTheDocument();
    expect(realBuilds()).toBe(1);
    first.unmount();

    render(<MapPage data={data(DIMS)} callbacks={{}} />);
    expect(realBuilds()).toBe(1);
  });

  it('rebuilds when the payload changes', () => {
    buildFileTree.mockClear();
    const fresh = [{ ...DIMS[0], violations: [...DIMS[0].violations] }];
    render(<MapPage data={data(fresh)} callbacks={{}} />);
    expect(realBuilds()).toBe(1);
  });
});
