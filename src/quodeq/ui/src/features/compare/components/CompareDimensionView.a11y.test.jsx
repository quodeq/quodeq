import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDimensionView from './CompareDimensionView.jsx';
import { DIMENSION_PANEL_ID, dimensionTabId } from './CompareDimensionHeader.jsx';
import { buildRow, buildDimensionView } from '../compareModel.js';
import { NOW, makeSummary, makeProject, DIM_SEC, DIM_USE } from '../_compareModel.fixtures.js';

const board = [
  { key: 'security', label: 'Security' },
  { key: 'usability', label: 'Usability' },
];

// Three principles, because the radar panel only draws a polygon at 3+ and
// the test asserts the panel really wraps the whole dimension body.
const secDim = (score) => ({
  ...DIM_SEC(score),
  principles: [
    { principle: 'Integrity', score: `${score}` },
    { principle: 'Confidentiality', score: `${score - 1}` },
    { principle: 'Authenticity', score: `${score - 2}` },
  ],
});

function makeView() {
  const summaries = {
    a: makeSummary({ dims: [secDim(6), DIM_USE(8)] }),
    b: makeSummary({ dims: [secDim(8), DIM_USE(5)] }),
  };
  const rows = ['a', 'b'].map((id) => buildRow(makeProject({ id }), summaries[id], NOW));
  return buildDimensionView('security', rows, NOW, summaries);
}

const renderView = () => render(
  <CompareDimensionView
    view={makeView()}
    board={board}
    fleet={null}
    onOpenDimension={vi.fn()}
    onOpenProject={vi.fn()}
    onOpenPrinciple={vi.fn()}
    onOpenProjectDimension={vi.fn()}
  />,
);

describe('CompareDimensionView accessibility (#6521)', () => {
  it('renders the dimension body as the tab panel the tabs control', () => {
    renderView();
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveAttribute('id', DIMENSION_PANEL_ID);
    expect(panel).toHaveAttribute('aria-labelledby', dimensionTabId('security'));
  });

  it('labels the panel with the tab that is actually selected', () => {
    renderView();
    const selected = screen.getByRole('tab', { selected: true });
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', selected.id);
    expect(screen.getByRole('tabpanel')).toContainElement(screen.getByRole('img', { name: /Radar chart/ }));
  });
});
