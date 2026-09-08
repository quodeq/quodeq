import { describe, it, expect } from 'vitest';
import { buildRadarSeries, buildDimensionMatrixRows } from './CompareDimensionView.jsx';
import { buildRow, buildDimensionView } from '../compareModel.js';
import { NOW, makeSummary, makeProject, DIM_SEC } from '../_compareModel.fixtures.js';

// The pure builders behind the drill-down. view.principles is label-sorted
// while each standing lists its principles in report order, so both have to
// pick scores by key, never by position.
function makeView() {
  const secNoConf = { ...DIM_SEC(7), principles: [{ principle: 'Integrity', score: '7' }] };
  const summaries = {
    a: makeSummary({ dims: [DIM_SEC(6)] }),
    b: makeSummary({ dims: [DIM_SEC(8)] }),
    c: makeSummary({ dims: [secNoConf] }),
  };
  const rows = ['a', 'b', 'c'].map((id) => buildRow(makeProject({ id }), summaries[id], NOW));
  return buildDimensionView('security', rows, NOW, summaries);
}

describe('buildRadarSeries', () => {
  it('reads each plotted standing by principle key, null where it has no score', () => {
    const view = makeView();
    expect(view.principles.map((p) => p.key)).toEqual(['confidentiality', 'integrity']);
    const byVariant = Object.fromEntries(buildRadarSeries(view, 'c').map((s) => [s.variant, s.values]));
    expect(byVariant.average).toEqual([6, 7]);
    expect(byVariant.lead).toEqual([7, 8]);
    expect(byVariant.trail).toEqual([5, 6]);
    expect(byVariant.focus).toEqual([null, 7]);
  });

  it('recolors a hovered lead/trail instead of plotting it twice', () => {
    const view = makeView();
    const series = buildRadarSeries(view, 'b');
    expect(series.map((s) => s.variant)).toEqual(['average', 'trail', 'lead']);
    expect(series.find((s) => s.variant === 'lead').focused).toBe(true);
  });

  it('plots the first of two principles that collapse to one key', () => {
    // 'Error Handling' and 'error handling' share a nameKey; the axis shows
    // the first spelling's score, like the find() the Map replaced.
    const dim = {
      ...DIM_SEC(8),
      principles: [
        { principle: 'Error Handling', score: '8' },
        { principle: 'error handling', score: '2' },
      ],
    };
    const summaries = { a: makeSummary({ dims: [dim] }) };
    const view = buildDimensionView('security', [buildRow(makeProject({ id: 'a' }), summaries.a, NOW)], NOW, summaries);
    expect(view.principles.map((p) => p.key)).toEqual(['error handling']);
    const lead = buildRadarSeries(view, null).find((s) => s.variant === 'lead');
    expect(lead.values).toEqual([8]);
  });
});

describe('buildDimensionMatrixRows', () => {
  it('fills one cell per principle key, empty where the project has no score, clicks opening that cell', () => {
    const view = makeView();
    const opened = [];
    const rows = buildDimensionMatrixRows(view, () => {}, (cell) => opened.push(cell));
    expect(rows.map((r) => r.id)).toEqual(['b', 'c', 'a']);
    const c = rows.find((r) => r.id === 'c');
    expect(c.cells.confidentiality).toEqual({ score: null });
    expect(c.cells.integrity.score).toBe(7);
    c.cells.integrity.onClick();
    expect(opened).toHaveLength(1);
    expect(opened[0]).toMatchObject({ id: 'c', score: 7 });
    const b = rows.find((r) => r.id === 'b');
    expect(b.cells.confidentiality.score).toBe(7);
    expect(b.cells.integrity.score).toBe(8);
  });

  it('leaves cells unclickable without an onOpenPrinciple handler', () => {
    const rows = buildDimensionMatrixRows(makeView(), () => {}, undefined);
    expect(rows[0].cells.integrity.onClick).toBeUndefined();
  });

  it('fills a cell from the first perProject entry when a project appears twice', () => {
    // Defensive first-wins: a payload that slipped two entries for one
    // project past the board builder must not flip the cell to the later one.
    const row = { id: 'a', name: 'proj-a', remote: false };
    const view = {
      standings: [{ row, score: 6 }],
      principles: [{
        key: 'error handling',
        label: 'error handling',
        perProject: [{ id: 'a', score: 6 }, { id: 'a', score: 3 }],
      }],
    };
    const rows = buildDimensionMatrixRows(view, () => {}, undefined);
    expect(rows).toHaveLength(1);
    expect(rows[0].cells['error handling'].score).toBe(6);
  });
});
