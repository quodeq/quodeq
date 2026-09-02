/**
 * Head-to-head duel view builder for the Compare tab. Split out of
 * compareModel.js — see compareModel.js for the module-level docs.
 */
import { sortedByDate, round1 } from './compareModel.js';

const gapOf = (x, y) => (x != null && y != null ? round1(x - y) : null);

/**
 * Dimension union: a dimension only one side has still renders (gapless);
 * `shared` gates the principle diff below, which needs both sides.
 */
function _diffDimensions(a, b) {
  const keys = new Map();
  for (const d of a.dims.concat(b.dims)) {
    if (!keys.has(d.key)) keys.set(d.key, d.label);
  }
  return Array.from(keys, ([key, label]) => {
    const da = a.dims.find((d) => d.key === key);
    const db = b.dims.find((d) => d.key === key);
    const scoreA = da?.score ?? null;
    const scoreB = db?.score ?? null;
    return {
      key,
      label,
      a: scoreA,
      b: scoreB,
      gap: gapOf(scoreA, scoreB),
      shared: scoreA != null && scoreB != null,
    };
  }).sort((x, y) => x.label.localeCompare(y.label));
}

/** Per-principle diffs, one group per shared dimension. */
function _diffPrinciples(dimensions, a, b) {
  return dimensions
    .filter((d) => d.shared)
    .map((dim) => {
      const pa = a.dims.find((d) => d.key === dim.key)?.principles || [];
      const pb = b.dims.find((d) => d.key === dim.key)?.principles || [];
      const pKeys = new Map();
      for (const p of pa.concat(pb)) {
        if (p.score != null && !pKeys.has(p.key)) pKeys.set(p.key, p.label);
      }
      const items = Array.from(pKeys, ([key, label]) => {
        const scoreA = pa.find((p) => p.key === key)?.score ?? null;
        const scoreB = pb.find((p) => p.key === key)?.score ?? null;
        return { key, label, a: scoreA, b: scoreB, gap: gapOf(scoreA, scoreB) };
      }).sort((x, y) => x.label.localeCompare(y.label));
      return { key: dim.key, label: dim.label, items };
    })
    .filter((g) => g.items.length);
}

// One point per DAY, keeping the day's newest run: several runs in one
// afternoon otherwise draw vertical zigzags that read as noise, not trend.
// Same collapse the Overview's day view applies.
function _buildDuelSeries(id, summariesById) {
  const daily = new Map();
  for (const e of sortedByDate(summariesById?.[id]?.trend)) {
    daily.set(String(e.dateISO).slice(0, 10), e);
  }
  return Array.from(daily.values()).map((e) => ({ dateISO: e.dateISO, value: e.numericAverage }));
}

/**
 * Head-to-head model for exactly two projects ("compare these two").
 * Gap convention throughout: left minus right (a minus b), so a positive
 * gap always means the left project leads. Returns null when either id is
 * not in `rows`.
 */
export function buildDuelView(idA, idB, rows, now, summariesById) {
  const a = rows.find((r) => r.id === idA);
  const b = rows.find((r) => r.id === idB);
  if (!a || !b) return null;

  const dimensions = _diffDimensions(a, b);
  const principles = _diffPrinciples(dimensions, a, b);

  return {
    a,
    b,
    ready: a.hasData && b.hasData,
    gap: gapOf(a.score, b.score),
    dimensions,
    sharedCount: dimensions.filter((d) => d.shared).length,
    principles,
    trend: { a: _buildDuelSeries(idA, summariesById), b: _buildDuelSeries(idB, summariesById) },
  };
}
