import test from 'node:test';
import assert from 'node:assert/strict';
import { STEADY, buildDirectionMap } from './compareDirectionMap.js';

const box = { left: 16, top: 18, width: 600, height: 280 };
const row = (name, score, delta, totalFiles = 100, stale = false) => ({ name, score, delta, totalFiles, stale });
const inside = (v, lo, hi) => v >= lo - 1e-9 && v <= hi + 1e-9;

test('buildDirectionMap: the view fits the projects, so an all-improving fleet puts "no change" near the left edge', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, 1.2), row('b', 8, 2.4), row('c', 7, 1.8)], fleetScore: 8, box });
  const xs = m.points.map((p) => p.cx);
  assert.ok(xs.every((x) => inside(x, box.left, box.left + box.width)));
  assert.ok(m.zeroX < box.left + box.width * 0.2, `zeroX ${m.zeroX}`);
  // The projects, not 0, fill the plot: their spread covers most of the width.
  assert.ok(Math.max(...xs) - Math.min(...xs) > box.width * 0.4);
});

test('buildDirectionMap: both references stay inside the plot', () => {
  const m = buildDirectionMap({ rows: [row('a', 9.5, -1.5), row('b', 6.5, -0.4)], fleetScore: 8.1, box });
  assert.ok(inside(m.zeroX, box.left, box.left + box.width));
  assert.ok(inside(m.fleetY, box.top, box.top + box.height));
});

test('buildDirectionMap: projects with no runs in the window are plotted on "no change", marked still', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, 0.5), row('quiet', 8, null)], fleetScore: 8.5, box });
  const quiet = m.points.find((p) => p.row.name === 'quiet');
  assert.equal(quiet.still, true);
  assert.ok(Math.abs(quiet.cx - m.zeroX) < 1e-9);
  assert.equal(m.points.find((p) => p.row.name === 'a').still, false);
});

test('buildDirectionMap: bigger projects get bigger dots and paint first', () => {
  const m = buildDirectionMap({ rows: [row('small', 8, 0.1, 10), row('big', 8, 0.2, 1000)], fleetScore: 8, box });
  assert.equal(m.points[0].row.name, 'big');
  assert.ok(m.points[0].r > m.points[1].r);
});

test('buildDirectionMap: the steady band spans ±STEADY around "no change", clipped to the plot', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, -1), row('b', 8, 1)], fleetScore: 8, box });
  assert.ok(Math.abs((m.zeroX - m.steady.x1) - (m.steady.x2 - m.zeroX)) < 1e-9);
  assert.ok(STEADY > 0);
  const edge = buildDirectionMap({ rows: [row('a', 9, 2), row('b', 8, 3)], fleetScore: 8, box });
  assert.ok(edge.steady.x1 >= box.left);
});

test('buildDirectionMap: ticks are round steps inside the range', () => {
  const m = buildDirectionMap({ rows: [row('a', 9.5, 1), row('b', 6.5, -1)], fleetScore: 8.1, box });
  assert.ok(m.ticks.move.some((tk) => tk.d === 0));
  assert.ok(m.ticks.move.every((tk) => inside(tk.x, box.left, box.left + box.width)));
  assert.ok(m.ticks.score.every((tk) => Number.isInteger(tk.v * 2)));
});

test('buildDirectionMap: labels of neighbouring dots never overlap', () => {
  const rows = [row('quodeq', 8.9, 0.9, 3900), row('shaka-player', 8.9, 1.9, 700), row('third-project', 8.8, 1.4, 50)];
  const m = buildDirectionMap({ rows, fleetScore: 8, box });
  const labels = m.points.map((p) => p.label);
  for (let i = 0; i < labels.length; i += 1) {
    for (let j = i + 1; j < labels.length; j += 1) {
      const a = labels[i];
      const b = labels[j];
      const overlap = a.x1 < b.x2 && a.x2 > b.x1 && Math.abs(a.y - b.y) < 12;
      assert.equal(overlap, false, `${m.points[i].row.name} vs ${m.points[j].row.name}`);
    }
  }
});
