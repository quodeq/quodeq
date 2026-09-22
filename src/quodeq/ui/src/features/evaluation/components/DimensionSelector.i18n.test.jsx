import { describe, it, expect, vi, afterEach } from 'vitest';
import { render } from '@testing-library/react';

// The app has no runtime language switch yet, so a catalog swap stands in for
// one: t() resolves through this table first and falls back to en.json. What
// matters is that a label re-resolves on the next render instead of staying
// frozen at whatever the catalog said when the module was first imported.
const catalog = vi.hoisted(() => ({ current: {} }));

vi.mock('../../../strings/index.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    t: (key, vars) => (Object.hasOwn(catalog.current, key) ? catalog.current[key] : actual.t(key, vars)),
  };
});

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import DimensionSelector from './DimensionSelector.jsx';

const DIMS = [{ id: 'maint', label: 'Maintainability', standardType: 'quodeq' }];

function renderSelector(variant) {
  return render(
    <DimensionSelector
      allDimensions={DIMS}
      selectedDims={new Set()}
      onToggle={() => {}}
      onSelectAll={() => {}}
      onClearAll={() => {}}
      variant={variant}
    />,
  );
}

describe('DimensionSelector standard-type labels', () => {
  afterEach(() => { catalog.current = {}; });

  it('chips variant re-resolves the type label when the catalog changes', () => {
    const { container, rerender } = renderSelector('chips');
    expect(container.querySelector('.dimension-chip-type').textContent).toBe('Quodeq');

    catalog.current = { 'evaluate.stdQuodeq': 'Quodeq (nl)' };
    rerender(
      <DimensionSelector allDimensions={[...DIMS]} selectedDims={new Set()} onToggle={() => {}} onSelectAll={() => {}} onClearAll={() => {}} variant="chips" />,
    );
    expect(container.querySelector('.dimension-chip-type').textContent).toBe('Quodeq (nl)');
  });

  it('terminal variant re-resolves the type label when the catalog changes', () => {
    const { container, rerender } = renderSelector('terminal');
    expect(container.querySelector('.eval-dim-card__std').textContent).toBe('quodeq');

    catalog.current = { 'evaluate.stdQuodeq': 'Kwaliteit' };
    rerender(
      <DimensionSelector allDimensions={[...DIMS]} selectedDims={new Set()} onToggle={() => {}} onSelectAll={() => {}} onClearAll={() => {}} variant="terminal" />,
    );
    expect(container.querySelector('.eval-dim-card__std').textContent).toBe('kwaliteit');
  });

  it('a dimension with an unknown standard type still falls back to the ISO label', () => {
    const { container } = render(
      <DimensionSelector
        allDimensions={[{ id: 'x', label: 'X', standardType: 'other' }]}
        selectedDims={new Set()}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onClearAll={() => {}}
        variant="chips"
      />,
    );
    expect(container.querySelector('.dimension-chip-type').textContent).toBe('ISO');
  });
});
