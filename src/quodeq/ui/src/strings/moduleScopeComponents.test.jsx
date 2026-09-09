// Companion to moduleScope.test.js: two more catalogs are built at MODULE
// scope by calling t()/tRich() while their module initializes, not inside a
// render -- DimensionSelector.jsx's TYPE_CONFIG/DEFAULT_TYPE_CONFIG and
// OmlxTab.jsx's OMLX_MODEL_HINT. moduleScope.test.js can't cover these: it
// uses node:test and asserts on the raw catalog values, but neither of
// these two modules exports its module-scope constant, and OMLX_MODEL_HINT
// is JSX (from tRich), not a string. Rendering the owning component is the
// only way to observe whether the value froze as the key.
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../api/ApiContext.jsx';
import DimensionSelector from '../features/evaluation/components/DimensionSelector.jsx';
import OmlxTab from '../features/settings/components/OmlxTab.jsx';

/** A value that is still its own catalog key never got resolved. */
const RAW_KEY = /^[a-z]+(\.[a-zA-Z]+)+$/;

const DIMS = [
  { id: 'd1', label: 'Dim One', standardType: 'quodeq' },
  { id: 'd2', label: 'Dim Two', standardType: 'custom' },
  { id: 'd3', label: 'Dim Three', standardType: 'community' },
  // No matching entry in TYPE_CONFIG -- exercises DEFAULT_TYPE_CONFIG.
  { id: 'd4', label: 'Dim Four', standardType: 'some-other-standard' },
];

describe('DimensionSelector type chip labels resolve at module init', () => {
  it('never renders a raw catalog key as a chip label', () => {
    const { container } = render(
      <DimensionSelector
        allDimensions={DIMS}
        selectedDims={new Set()}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onClearAll={() => {}}
      />,
    );
    const chips = container.querySelectorAll('.dimension-chip-type');
    expect(chips.length).toBe(DIMS.length);
    for (const chip of chips) {
      expect(chip.textContent.length).toBeGreaterThan(0);
      expect(chip.textContent).not.toMatch(RAW_KEY);
    }
  });
});

const fakeApi = {
  getOmlxModels: vi.fn().mockResolvedValue([]),
  testOmlxConcurrency: vi.fn(),
  // useOmlxServerStatus depends on this; return offline by default.
  getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('OmlxTab model hint resolves at module init', () => {
  it('never renders the raw catalog key in the help popover', () => {
    const Wrapper = makeWrapper();
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { getByRole } = render(
      <Wrapper>
        <OmlxTab state={state} update={vi.fn()} />
      </Wrapper>,
    );
    fireEvent.click(getByRole('button', { name: 'Model help' }));
    const tooltip = getByRole('tooltip');
    expect(tooltip.textContent.length).toBeGreaterThan(0);
    expect(tooltip.textContent).not.toMatch(RAW_KEY);
  });
});
