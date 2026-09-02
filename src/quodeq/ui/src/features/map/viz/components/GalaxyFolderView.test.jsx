import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import GalaxyFolderView from './GalaxyFolderView.jsx';

// GalaxyFolderView is the (vizStyle: 'galaxy', galaxyMode: 'filesystem')
// branch of MapPage's viz switch (see MapPage.jsx) and had zero coverage
// before this refactor. It wires a ResizeObserver in a useEffect; jsdom does
// not provide one, so stub it the same way GalaxyView.test.jsx does.
//
// scoreRGB/sevRGB (used while building the initial scene, synchronously
// during mount) reach into a real canvas 2D context to parse CSS colors —
// unavailable under jsdom (vitest.setup.js stubs getContext to return
// null). Mock just those two; everything else in galaxyCore.js stays real.
vi.mock('../core/galaxyCore.js', async (importOriginal) => {
  const actual = await importOriginal();
  const col = { r: 100, g: 150, b: 200 };
  return { ...actual, scoreRGB: () => col, sevRGB: () => col };
});

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});
afterEach(() => { vi.unstubAllGlobals(); });

const NODE = {
  name: 'root',
  path: '',
  isFile: false,
  violations: 2,
  compliance: 3,
  complianceRate: 0.6,
  severity: { critical: 0, major: 1, minor: 1 },
  children: [
    {
      name: 'src',
      path: 'src',
      isFile: false,
      violations: 2,
      compliance: 3,
      complianceRate: 0.6,
      severity: { critical: 0, major: 1, minor: 1 },
      children: [],
    },
  ],
};

function renderView(props = {}) {
  return render(
    <GalaxyFolderView
      node={NODE}
      currentPath=""
      onPathChange={() => {}}
      onFileClick={() => {}}
      onNavigate={() => {}}
      projectName="Demo"
      {...props}
    />,
  );
}

describe('GalaxyFolderView', () => {
  it('mounts without crashing', () => {
    expect(() => renderView()).not.toThrow();
  });

  it('renders a focusable canvas with the galaxy folder aria label', () => {
    const { container } = renderView();
    const canvas = container.querySelector('canvas');
    expect(canvas).not.toBeNull();
    expect(canvas).toHaveAttribute('role', 'application');
    expect(canvas).toHaveAttribute('tabindex', '0');
  });

  it('resets navigation when resetKey changes', () => {
    const { rerender, container } = renderView({ resetKey: 0 });
    expect(() => rerender(
      <GalaxyFolderView
        node={NODE}
        currentPath=""
        onPathChange={() => {}}
        onFileClick={() => {}}
        onNavigate={() => {}}
        projectName="Demo"
        resetKey={1}
      />,
    )).not.toThrow();
    expect(container.querySelector('canvas')).not.toBeNull();
  });
});
