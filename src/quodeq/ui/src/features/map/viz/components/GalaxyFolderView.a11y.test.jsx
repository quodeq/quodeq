/**
 * Accessibility tests for GalaxyFolderView.
 * 6424: star selection ran through mouse hit-testing only, so a keyboard
 * user could pan the camera but never reach a file. The view now renders a
 * ChartKeyboardControls layer over the file stars, reaching the same
 * handleNodeClick the click path uses.
 *
 * Same jsdom stubs as GalaxyFolderView.test.jsx: no ResizeObserver, and
 * scoreRGB/sevRGB parse CSS colors through a real canvas context.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import GalaxyFolderView from './GalaxyFolderView.jsx';
import { handleNodeClick } from './galaxyFolderClickHandlers.js';

vi.mock('../core/galaxyCore.js', async (importOriginal) => {
  const actual = await importOriginal();
  const col = { r: 100, g: 150, b: 200 };
  return { ...actual, scoreRGB: () => col, sevRGB: () => col };
});

vi.mock('./galaxyFolderClickHandlers.js', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, handleNodeClick: vi.fn() };
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});
afterEach(() => { vi.unstubAllGlobals(); });

function file(name, violations) {
  return { name, path: name, isFile: true, violations, compliance: 1, complianceRate: 0.5, severity: { critical: 0, major: violations, minor: 0 }, children: [] };
}

const NODE = {
  name: 'root', path: '', isFile: false,
  violations: 3, compliance: 3, complianceRate: 0.5,
  severity: { critical: 0, major: 2, minor: 1 },
  children: [
    file('a.js', 2),
    file('b.js', 1),
    {
      name: 'src', path: 'src', isFile: false,
      violations: 0, compliance: 1, complianceRate: 1,
      severity: { critical: 0, major: 0, minor: 0 },
      children: [file('c.js', 0), file('d.js', 0)],
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

describe('GalaxyFolderView keyboard star layer (6424)', () => {
  it('renders one focusable control per star, under a named group', () => {
    renderView();
    const group = screen.getByLabelText('Contents of this folder');
    expect(group).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'a.js: 2 violations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'b.js: 1 violations' })).toBeInTheDocument();
  });

  it('lists the folder stars too, since they are hit-tested as well', () => {
    renderView();
    expect(screen.getByRole('button', { name: 'src: 0 violations' })).toBeInTheDocument();
  });

  it('activating a control opens that star through the click path', () => {
    renderView();
    fireEvent.click(screen.getByRole('button', { name: 'a.js: 2 violations' }));
    expect(handleNodeClick).toHaveBeenCalledTimes(1);
    const [, hover] = handleNodeClick.mock.calls[0];
    expect(hover.type).toBe('file');
    expect(hover.data.path).toBe('a.js');
  });

  it('opens a folder star as a folder', () => {
    renderView();
    fireEvent.click(screen.getByRole('button', { name: 'src: 0 violations' }));
    const [, hover] = handleNodeClick.mock.calls[0];
    expect(hover.type).toBe('folder');
    expect(hover.data.path).toBe('src');
  });

  it('activates from the keyboard too', () => {
    renderView();
    const button = screen.getByRole('button', { name: 'b.js: 1 violations' });
    fireEvent.keyDown(button, { key: 'Enter' });
    expect(handleNodeClick).toHaveBeenCalledTimes(1);
    expect(handleNodeClick.mock.calls[0][1].data.path).toBe('b.js');
  });

  it('resolves the star by path, so a star index shifting cannot open another file', () => {
    renderView();
    for (const name of ['a.js: 2 violations', 'b.js: 1 violations', 'src: 0 violations']) {
      handleNodeClick.mockClear();
      fireEvent.click(screen.getByRole('button', { name }));
      const [, hover] = handleNodeClick.mock.calls[0];
      expect(name.startsWith(`${hover.data.path}:`)).toBe(true);
      expect(hover.starIdx).toBeGreaterThanOrEqual(0);
    }
  });
});
