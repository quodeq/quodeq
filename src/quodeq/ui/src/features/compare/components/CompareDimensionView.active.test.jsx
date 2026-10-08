import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import CompareDimensionView from './CompareDimensionView.jsx';
import { buildRow, buildDimensionView } from '../compareModel.js';
import { NOW, makeSummary, makeProject, DIM_SEC } from '../_compareModel.fixtures.js';

// One project is active across the whole drill-down: the hovered row in
// any panel, else the app's selected project. The radar plots it, the
// standings and matrix rows highlight it, and the principle cards mark its
// bar and name its score.
const board = [{ key: 'security', label: 'Security' }];

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
    a: makeSummary({ dims: [secDim(6)] }),
    b: makeSummary({ dims: [secDim(8)] }),
    c: makeSummary({ dims: [secDim(7)] }),
  };
  const rows = ['a', 'b', 'c'].map((id) => buildRow(makeProject({ id, name: `proj-${id}`, displayName: `proj-${id}` }), summaries[id], NOW));
  return buildDimensionView('security', rows, NOW, summaries);
}

const renderView = (selectedProject) => render(
  <CompareDimensionView
    view={makeView()}
    board={board}
    selectedProject={selectedProject}
    onOpenDimension={vi.fn()}
    onOpenProject={vi.fn()}
    onOpenPrinciple={vi.fn()}
    onOpenProjectDimension={vi.fn()}
  />,
);

const activeStandingName = (container) => container.querySelector('.compare-standings__row.is-active .compare-standings__name')?.textContent;
const activeMatrixName = (container) => container.querySelector('.compare-matrix tbody tr.is-active .compare-matrix__rowbtn')?.textContent;
const legendProject = (container) => container.querySelector('.compare-radar__legendItem--project')?.textContent;
const activeSlots = (container) => container.querySelectorAll('.compare-principle__slot.is-active');

describe('CompareDimensionView active project', () => {
  it('highlights the selected project everywhere by default', () => {
    const { container } = renderView('a');
    expect(activeStandingName(container)).toBe('proj-a');
    expect(activeMatrixName(container)).toBe('proj-a');
    expect(legendProject(container)).toBe('proj-a');
    expect(container.querySelectorAll('.compare-radar__poly--project')).toHaveLength(1);
    expect(container.querySelectorAll('.compare-radar__poly--average')).toHaveLength(1);
    // One active bar per principle card, and the card names its score.
    expect(activeSlots(container)).toHaveLength(3);
    expect(container.querySelectorAll('.compare-principle__activeName')[0]).toHaveTextContent('proj-a');
    expect(container.querySelectorAll('.compare-principle__activeScore')[0]).toHaveTextContent('4.0');
  });

  it('falls back to the leader when the selection is outside the scope', () => {
    const { container } = renderView('elsewhere');
    expect(activeStandingName(container)).toBe('proj-b');
    expect(legendProject(container)).toBe('proj-b');
  });

  it('moves the highlight to a hovered standings row and back on leave', () => {
    const { container } = renderView('a');
    const rows = container.querySelectorAll('.compare-standings__row');
    const rowC = Array.from(rows).find((r) => r.textContent.includes('proj-c'));
    fireEvent.mouseEnter(rowC);
    expect(activeStandingName(container)).toBe('proj-c');
    expect(activeMatrixName(container)).toBe('proj-c');
    expect(legendProject(container)).toBe('proj-c');
    expect(container.querySelectorAll('.compare-standings__row.is-active')).toHaveLength(1);
    fireEvent.mouseLeave(rowC);
    expect(activeStandingName(container)).toBe('proj-a');
  });

  it('a hovered matrix row drives the same highlight', () => {
    const { container } = renderView('a');
    const trs = container.querySelectorAll('.compare-matrix tbody tr');
    const trB = Array.from(trs).find((r) => r.textContent.includes('proj-b'));
    fireEvent.mouseEnter(trB);
    expect(activeStandingName(container)).toBe('proj-b');
    expect(legendProject(container)).toBe('proj-b');
    fireEvent.mouseLeave(trB.closest('table'));
    expect(activeStandingName(container)).toBe('proj-a');
  });

  it('a hovered principle bar drives the same highlight', () => {
    const { container } = renderView('a');
    const slot = Array.from(container.querySelectorAll('.compare-principle__slot'))
      .find((s) => s.getAttribute('aria-label').includes('proj-c'));
    fireEvent.mouseEnter(slot);
    expect(activeStandingName(container)).toBe('proj-c');
    expect(screen.getAllByText('proj-c').length).toBeGreaterThan(1);
  });
});
