import test from 'node:test';
import assert from 'node:assert/strict';
import { STEADY, buildDirectionMap } from './compareDirectionMap.js';

const box = { left: 16, top: 18, width: 600, height: 280 };
const row = (name, score, delta, totalFiles = 100, stale = false) => ({ name, score, delta, totalFiles, stale });

test('buildDirectionMap: 0 movement is the exact horizontal centre, the fleet average the vertical one', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, 1.2), row('b', 6, -0.4)], fleetScore: 7.5, box });
  assert.ok(Math.abs(m.center.x - (box.left + box.width / 2)) < 1e-9);
  assert.ok(Math.abs(m.center.y - (box.top + box.height / 2)) < 1e-9);
});

test('buildDirectionMap: projects with no runs in the window are listed, not plotted', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, 0.5), row('quiet', 8, null)], fleetScore: 8.5, box });
  assert.deepEqual(m.points.map((p) => p.row.name), ['a']);
  assert.deepEqual(m.still.map((r) => r.name), ['quiet']);
});

test('buildDirectionMap: bigger projects get bigger dots and paint first', () => {
  const m = buildDirectionMap({ rows: [row('small', 8, 0.1, 10), row('big', 8, 0.2, 1000)], fleetScore: 8, box });
  assert.equal(m.points[0].row.name, 'big');
  assert.ok(m.points[0].r > m.points[1].r);
});

test('buildDirectionMap: the steady band spans ±STEADY around the centre', () => {
  const m = buildDirectionMap({ rows: [row('a', 9, 1)], fleetScore: 8, box });
  assert.ok(Math.abs((m.center.x - m.steady.x1) - (m.steady.x2 - m.center.x)) < 1e-9);
  assert.ok(STEADY > 0);
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

test('buildDirectionMap: no score tick sits on the fleet-average axis', () => {
  const m = buildDirectionMap({ rows: [row('a', 9.5, 1), row('b', 6.5, -1)], fleetScore: 8.1, box });
  assert.ok(m.ticks.score.every((t) => Math.abs(t.v - 8.1) > 0.3));
});
