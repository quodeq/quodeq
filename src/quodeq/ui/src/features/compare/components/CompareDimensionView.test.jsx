import { describe, it, expect } from 'vitest';
import { buildRadarSeries, resolveActiveStanding } from './CompareDimensionView.jsx';
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

const standingOf = (view, id) => view.standings.find((s) => s.row.id === id);

describe('resolveActiveStanding', () => {
  it('prefers the hovered row, then the selected project, then the leader', () => {
    const view = makeView();
    expect(resolveActiveStanding(view, 'c', 'a')).toBe(standingOf(view, 'c'));
    expect(resolveActiveStanding(view, null, 'a')).toBe(standingOf(view, 'a'));
    expect(resolveActiveStanding(view, null, 'not-in-scope')).toBe(view.lead);
    expect(resolveActiveStanding(view, null, null)).toBe(view.lead);
  });
});

describe('buildRadarSeries', () => {
  it('plots the scope average and the active standing by principle key, null where it has no score', () => {
    const view = makeView();
    expect(view.principles.map((p) => p.key)).toEqual(['confidentiality', 'integrity']);
    const series = buildRadarSeries(view, standingOf(view, 'c'));
    expect(series.map((s) => s.variant)).toEqual(['average', 'project']);
    expect(series[0].values).toEqual([6, 7]);
    expect(series[1].values).toEqual([null, 7]);
  });

  it('plots only the average without an active standing', () => {
    const view = makeView();
    expect(buildRadarSeries(view, null).map((s) => s.variant)).toEqual(['average']);
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
    const project = buildRadarSeries(view, view.lead).find((s) => s.variant === 'project');
    expect(project.values).toEqual([8]);
  });
});
