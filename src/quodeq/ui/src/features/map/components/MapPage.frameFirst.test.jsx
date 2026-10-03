import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import MapPage from './MapPage.jsx';

// The Map is the heaviest tab: the file tree over every finding, then the
// pack layout, then one SVG node per circle. Its first commit must be the
// frame alone (header, controls, an empty slot), with the tree build and
// the visualisation following in a later commit.

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

function data() {
  return {
    accumulated: { dimensions: DIMS }, dashboard: null, projectName: 'p1',
    projects: [{ id: 'p1', name: 'p1' }], projectsLoaded: true,
    selectedProject: 'p1', selectedSource: 'local', loading: false, isFetching: false,
  };
}

describe('MapPage paints its frame first', () => {
  it('builds the tree from nothing on the first commit and from the findings only after', () => {
    buildFileTree.mockClear();
    render(<MapPage data={data()} callbacks={{}} />);
    const sizes = buildFileTree.mock.calls.map(([dims]) => dims.length);
    expect(sizes[0]).toBe(0);
    expect(sizes.at(-1)).toBe(DIMS.length);
    // Once the findings are in, no commit goes back to the empty tree.
    const firstReal = sizes.indexOf(DIMS.length);
    expect(sizes.slice(firstReal).every((n) => n === DIMS.length)).toBe(true);
  });

  it('settles on the visualisation once the deferred body mounts', () => {
    const { container } = render(<MapPage data={data()} callbacks={{}} />);
    expect(container.querySelector('.term-header')).toBeInTheDocument();
    expect(container.querySelector('.map-viz-container--skeleton')).toBeNull();
    expect(container.querySelector('.map-viz-container')).toBeInTheDocument();
    expect(container.textContent).toContain('2 violations');
  });
});
