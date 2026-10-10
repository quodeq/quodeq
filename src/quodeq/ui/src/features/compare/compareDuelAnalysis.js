/**
 * The head-to-head screen's analysis: pure functions over buildDuelView's
 * model, one per question the screen answers.
 *
 *   duelSignal         is the gap bigger than the run-to-run swing?
 *   comparabilityChecks is this a fair comparison at all?
 *   gapContributions   where does the overall gap come from?
 *   principleMap       which principles differ, and what do both get wrong?
 *   exposureOf         violations normalised by size, pass rate
 *
 * Nothing here fetches or formats for display; components own the words.
 */
import { roundOneDecimal } from '../../utils/rounding.js';
import { MS_PER_DAY } from '../../utils/time.js';
import { PERCENT } from '../../constants.js';
import { getGradeThresholds } from '../../utils/gradeThresholds.js';

export const DUEL_SIGNAL = Object.freeze({
  CLEAR: 'clear',
  PROBABLE: 'probable',
  NOISE: 'noise',
  UNKNOWN: 'unknown',
});

export const DUEL_CHECK = Object.freeze({
  DIMENSIONS: 'dimensions',
  SCAN_GAP: 'scanGap',
  COMMITS: 'commits',
  SIZE: 'size',
  COVERAGE: 'coverage',
});

// Noise: median absolute change between consecutive daily scores over the
// latest NOISE_WINDOW points. Fewer than NOISE_MIN_POINTS says nothing.
const NOISE_WINDOW = 12;
const NOISE_MIN_POINTS = 4;
// A floor so a perfectly flat history does not make every gap "clear".
const NOISE_FLOOR = 0.1;
// Gap / combined noise at or above these reads clear / probable.
const CLEAR_RATIO = 2;
const PROBABLE_RATIO = 1;
// Scans further apart than this weaken the comparison.
const SCAN_GAP_OK_DAYS = 14;
// Analysed-file coverage differing by this many points or more is a caution.
const COVERAGE_GAP_OK = 15;
// A principle gap under this is "even": inside typical scoring wobble.
export const EVEN_BAND = 0.5;
// Shared weaknesses exclude pairs further apart than this: those are one
// side's edge, already listed there.
const SHARED_WEAKNESS_MAX_GAP = 1.5;
// Rows per principle list.
export const EDGE_LIST_SIZE = 5;
// The scatter needs this many points to show a pattern, not a dot.
export const MAP_MIN_POINTS = 6;
// Contributions smaller than this are rounding, not a "not shared" share.
const REST_EPSILON = 0.05;

/** Typical run-to-run swing of one daily series ({dateISO, value}[]), or null. */
export function noiseOf(series) {
  const values = series.slice(-NOISE_WINDOW).map((e) => e.value);
  if (values.length < NOISE_MIN_POINTS) return null;
  const steps = values.slice(1).map((v, i) => Math.abs(v - values[i])).sort((x, y) => x - y);
  return Math.max(NOISE_FLOOR, steps[Math.floor(steps.length / 2)]);
}

/** {level, ratio, noise}: the overall gap measured against both sides' noise. */
export function duelSignal(duel) {
  if (duel.gap == null) return null;
  const na = noiseOf(duel.trend.a);
  const nb = noiseOf(duel.trend.b);
  if (na == null || nb == null) return { level: DUEL_SIGNAL.UNKNOWN, ratio: null, noise: null };
  const noise = Math.hypot(na, nb);
  // Graded on the rounded ratio the reader sees: "2.0×" must never read
  // as merely probable because the float was 1.9999.
  const ratio = roundOneDecimal(Math.abs(duel.gap) / noise);
  let level = DUEL_SIGNAL.NOISE;
  if (ratio >= CLEAR_RATIO) level = DUEL_SIGNAL.CLEAR;
  else if (ratio >= PROBABLE_RATIO) level = DUEL_SIGNAL.PROBABLE;
  return { level, ratio, noise };
}

function scanGapDays(a, b) {
  const ta = Date.parse(a.lastISO);
  const tb = Date.parse(b.lastISO);
  if (!Number.isFinite(ta) || !Number.isFinite(tb)) return null;
  return Math.round(Math.abs(ta - tb) / MS_PER_DAY);
}

/**
 * The fairness strip: each check is {key, ok, params}. Components turn a
 * key + params into words; `ok: false` renders as a caution.
 */
export function comparabilityChecks(duel) {
  const { a, b } = duel;
  const total = duel.dimensions.length;
  const days = scanGapDays(a, b);
  const checks = [
    { key: DUEL_CHECK.DIMENSIONS, ok: duel.sharedCount === total, params: { shared: duel.sharedCount, total } },
    { key: DUEL_CHECK.SCAN_GAP, ok: days != null && days <= SCAN_GAP_OK_DAYS, params: { days } },
  ];
  for (const row of [a, b]) {
    if (row.commitsSince > 0) checks.push({ key: DUEL_CHECK.COMMITS, ok: false, params: { name: row.name, count: row.commitsSince } });
  }
  checks.push({ key: DUEL_CHECK.SIZE, ok: true, params: { a: a.totalFiles, b: b.totalFiles, langA: a.lang, langB: b.lang } });
  if (a.coveragePct != null && b.coveragePct != null) {
    checks.push({
      key: DUEL_CHECK.COVERAGE,
      ok: Math.abs(a.coveragePct - b.coveragePct) < COVERAGE_GAP_OK,
      params: { a: a.coveragePct, b: b.coveragePct },
    });
  }
  return checks;
}

/**
 * Each shared dimension's share of the overall gap. An overall score is the
 * mean of its dimensions, so a dimension contributes (a - b) / n; what the
 * shared ones do not explain (dimensions only one side has, rounding) is
 * the `rest` row. Sorted by size, rest last.
 */
export function gapContributions(duel) {
  const n = duel.dimensions.length;
  if (!n || duel.gap == null) return [];
  const rows = duel.dimensions
    .filter((d) => d.shared)
    .map((d) => ({ key: d.key, label: d.label, value: (d.a - d.b) / n, gap: d.gap, rest: false }))
    .sort((x, y) => Math.abs(y.value) - Math.abs(x.value));
  const rest = duel.gap - rows.reduce((s, r) => s + r.value, 0);
  if (Math.abs(rest) >= REST_EPSILON) rows.push({ key: 'rest', label: null, value: rest, gap: null, rest: true });
  return rows.map((r) => ({ ...r, value: roundOneDecimal(r.value) }));
}

/** The score a principle has to reach to count as good: the second tier. */
export function goodThreshold() {
  const tiers = getGradeThresholds();
  return tiers[Math.min(1, tiers.length - 1)][0];
}

/**
 * Every principle both sides scored, as scatter points, plus the lists the
 * screen reads off them: each side's biggest edges and the weaknesses both
 * share (both below good, and close to each other).
 */
export function principleMap(duel, good = goodThreshold()) {
  const points = duel.principles.flatMap((g) => g.items
    .filter((p) => p.a != null && p.b != null)
    .map((p) => ({ ...p, id: `${g.key}:${p.key}`, dimLabel: g.label })));
  const aAhead = points.filter((p) => p.gap >= EVEN_BAND);
  const bAhead = points.filter((p) => p.gap <= -EVEN_BAND);
  return {
    points,
    good,
    aEdges: [...aAhead].sort((x, y) => y.gap - x.gap).slice(0, EDGE_LIST_SIZE),
    bEdges: [...bAhead].sort((x, y) => x.gap - y.gap).slice(0, EDGE_LIST_SIZE),
    shared: points
      .filter((p) => p.a < good && p.b < good && Math.abs(p.gap) < SHARED_WEAKNESS_MAX_GAP)
      .sort((x, y) => (x.a + x.b) - (y.a + y.b))
      .slice(0, EDGE_LIST_SIZE),
    counts: { a: aAhead.length, b: bAhead.length, even: points.length - aAhead.length - bAhead.length },
  };
}

// Critical findings are rarer than violations: count them per 1,000 files.
const PER_THOUSAND = 1000;

/**
 * Exposure normalised by size (raw counts favour small projects):
 * violations per 100 analysed files, critical per 1,000, and pass rate.
 */
export function exposureOf(row) {
  const base = row.analyzedFiles || row.totalFiles;
  const checks = row.totalViolations + row.totalCompliance;
  return {
    per100: base ? (row.totalViolations / base) * PERCENT : null,
    criticalPerK: base ? ((row.severity?.critical ?? 0) / base) * PER_THOUSAND : null,
    passPct: checks ? Math.round((row.totalCompliance / checks) * PERCENT) : null,
    critical: row.severity?.critical ?? 0,
    major: row.severity?.major ?? 0,
  };
}
