import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
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

const legendProject = (container) => container.querySelector('.compare-radar__legendItem--project')?.textContent;
const tableRow = (container, name) => [...container.querySelectorAll('.compare-fleettable__row')].find((r) => r.textContent.includes(name));
const matrixTile = (container, name) => [...container.querySelectorAll('.compare-heat tbody tr')]
  .find((r) => r.textContent.includes(name))?.querySelector('.compare-heat__cell');

describe('CompareDimensionView active project', () => {
  it('draws the selected project on the radar by default', () => {
    const { container } = renderView('a');
    expect(legendProject(container)).toBe('proj-a');
  });

  it('falls back to the leader when the selection is outside the scope', () => {
    const { container } = renderView('zzz');
    expect(legendProject(container)).toBe('proj-b');
  });

  it('a hovered projects-table row redraws the radar, and leaving restores the selection', () => {
    const { container } = renderView('a');
    fireEvent.mouseEnter(tableRow(container, 'proj-c'));
    expect(legendProject(container)).toBe('proj-c');
    expect(tableRow(container, 'proj-c')).toHaveClass('is-hovered');
    fireEvent.mouseLeave(tableRow(container, 'proj-c'));
    expect(legendProject(container)).toBe('proj-a');
  });

  it('a hovered principle-matrix row drives the same radar', () => {
    const { container } = renderView('a');
    fireEvent.mouseEnter(matrixTile(container, 'proj-b'));
    expect(legendProject(container)).toBe('proj-b');
  });
});
