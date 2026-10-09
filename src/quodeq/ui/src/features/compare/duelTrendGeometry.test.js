import test from 'node:test';
import assert from 'node:assert/strict';
import { DUEL_SIDE, buildTrendGeometry } from './duelTrendGeometry.js';

const box = { left: 30, top: 10, width: 600, height: 200 };
const day = (n) => `2026-09-${String(n).padStart(2, '0')}T00:00:00Z`;
const now = Date.parse(day(30));

test('buildTrendGeometry: nothing to draw without parseable runs', () => {
  assert.equal(buildTrendGeometry({ a: [], b: [{ dateISO: 'nope', value: 7 }], box, now }), null);
});

test('buildTrendGeometry: the trend line ends on the real latest score', () => {
  const g = buildTrendGeometry({ a: [{ dateISO: day(1), value: 5 }, { dateISO: day(10), value: 9 }], b: [], box, now });
  assert.equal(g.sides.a.end.value, 9);
  assert.equal(g.sides.a.tail.y, g.sides.a.smooth.at(-1)[1]);
  assert.ok(g.sides.a.trend.startsWith('M'));
  assert.ok(g.sides.a.raw.includes('H'));
  assert.equal(g.sides.b, null);
});

test('buildTrendGeometry: fill is tinted by the leader and held after the newest run', () => {
  const g = buildTrendGeometry({
    a: [{ dateISO: day(1), value: 8 }, { dateISO: day(10), value: 8 }],
    b: [{ dateISO: day(1), value: 6 }, { dateISO: day(10), value: 6 }],
    box,
    now,
  });
  assert.ok(g.gaps.length >= 2);
  assert.ok(g.gaps.every((p) => p.lead === DUEL_SIDE.A));
  assert.equal(g.gaps.at(-1).held, true);
  assert.equal(g.gaps[0].held, false);
});

test('buildTrendGeometry: hover reports the real step values, not the smoothed ones', () => {
  const g = buildTrendGeometry({
    a: [{ dateISO: day(1), value: 5 }, { dateISO: day(5), value: 9 }],
    b: [{ dateISO: day(1), value: 6 }],
    box,
    now,
  });
  const px = box.left + box.width * 0.9;
  assert.deepEqual(g.valueAt(px), { a: 9, b: 6 });
});

test('buildTrendGeometry: a lone run is a dot, not a path', () => {
  const g = buildTrendGeometry({ a: [{ dateISO: day(3), value: 7 }], b: [], box, now });
  assert.equal(g.sides.a.trend, '');
  assert.ok(g.sides.a.single);
});
