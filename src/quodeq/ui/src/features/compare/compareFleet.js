/**
 * Fleet-wide row and aggregate builders for the Compare tab.
 *
 * Split out of compareModel.js (which keeps the shared primitives and
 * re-exports everything here) — see compareModel.js for the module-level
 * docs on inputs.
 */
import {
  STALE_AFTER_DAYS, nameKey, parseScore10, daysBetween, trendDelta, mean,
} from './compareModel.js';

// Consequence thresholds. The score scales as
// (10 - score) * log10(files + 10) * staleness, i.e. roughly 0..45 across
// realistic projects; these cuts put a failing large stale project in SEVERE
// and a healthy project of any size in CLEAR.
const SEVERE_AT = 18;
const ELEVATED_AT = 11;
const WATCH_AT = 6;
const STALE_FACTOR = 1.35;

function topLanguage(languageStats) {
  if (!languageStats || typeof languageStats !== 'object') return null;
  let best = null;
  for (const [lang, count] of Object.entries(languageStats)) {
    if (!best || count > best.count) best = { lang, count };
  }
  return best?.lang ?? null;
}

/**
 * Code moved since the last scored run -> the grade is provisional. Only
 * when the commit count is unknowable does plain age stand in for it.
 */
function _deriveStaleness(commitsSince, ageDays) {
  return commitsSince != null
    ? commitsSince > 0
    : ageDays != null && ageDays > STALE_AFTER_DAYS;
}

function _buildRowDims(summary) {
  return (summary?.dimensions || [])
    .map((d) => ({
      key: nameKey(d.dimension),
      label: String(d.dimension || '').toLowerCase(),
      // Raw identifiers for cross-project navigation: the dimension-eval
      // endpoint and the principle page need the payload's own spellings
      // and the run the numbers came from.
      name: d.dimension,
      fromRunId: d.fromRunId ?? null,
      fromDateLabel: d.fromDateLabel ?? null,
      score: parseScore10(d.overallScore),
      grade: d.overallGrade ?? null,
      violations: d.totals?.violationCount ?? 0,
      compliance: d.totals?.complianceCount ?? 0,
      severity: d.totals?.severity || { critical: 0, major: 0, minor: 0 },
      principles: (d.principles || []).map((p) => ({
        key: nameKey(p.principle || p.name),
        label: String(p.principle || p.name || '').toLowerCase(),
        name: p.principle || p.name || '',
        score: parseScore10(p.score),
      })),
    }))
    .filter((d) => d.key);
}

/**
 * One fleet-table row: a Project model joined with its compare summary.
 * `summary` may be undefined while the per-project query is in flight.
 */
export function buildRow(project, summary, now) {
  const id = project.id || project.name;
  const s = summary?.summary || null;
  const score = s?.numericAverage ?? null;
  const lastISO = summary?.lastRun?.dateISO || project.latestDate || null;
  const ageDays = lastISO ? daysBetween(lastISO, now) : null;
  const commitsSince = summary?.commitsSinceLastRun ?? null;
  const stale = _deriveStaleness(commitsSince, ageDays);
  const totalFiles = project.totalFiles ?? project.filesCount ?? null;
  const analyzedFiles = project.analyzedFiles ?? null;
  const { delta, lastDelta, spark } = trendDelta(summary?.trend, now);
  const dims = _buildRowDims(summary);
  return {
    id,
    // Remote (shared-repo) rows: `id` is the prefixed fleet-unique key, and
    // `sourceId` is the raw project id every API call and source-switching
    // navigation needs. Local rows keep sourceId === id.
    source: project.source === 'shared' ? 'shared' : 'local',
    sourceId: project.sourceId || id,
    remote: project.source === 'shared',
    name: project.displayName || project.name || id,
    lang: topLanguage(project.languageStats),
    totalFiles,
    analyzedFiles,
    coveragePct: totalFiles && analyzedFiles != null
      ? Math.round((analyzedFiles / totalFiles) * 100)
      : null,
    score,
    grade: s?.overallGrade ?? null,
    delta,
    lastDelta,
    spark,
    severity: s?.severity || { critical: 0, major: 0, minor: 0 },
    totalViolations: s?.totalViolations ?? 0,
    totalCompliance: s?.totalCompliance ?? 0,
    lastISO,
    stale,
    commitsSince,
    hasRuns: (project.runsCount ?? 0) > 0 || (summary?.runsCount ?? 0) > 0,
    loaded: summary !== undefined,
    hasData: score != null,
    dims,
  };
}

/** Higher = more deserving of attention. 0 for rows without a score. */
export function consequenceOf(row) {
  if (row.score == null) return 0;
  const sizeWeight = Math.log10((row.totalFiles ?? 0) + 10);
  const staleness = row.stale ? STALE_FACTOR : 1;
  return (10 - row.score) * sizeWeight * staleness;
}

export function consequenceLevel(value) {
  if (value >= SEVERE_AT) return 'severe';
  if (value >= ELEVATED_AT) return 'elevated';
  if (value >= WATCH_AT) return 'watch';
  return 'clear';
}

/**
 * Score ordering with a direction toggle. Rows without a score always sink
 * to the bottom, whichever direction is active — an unevaluated project is
 * not "the worst project".
 */
export function sortRows(rows, direction = 'desc') {
  const scored = rows.filter((r) => r.score != null)
    .sort((a, b) => (direction === 'asc' ? a.score - b.score : b.score - a.score));
  const unscored = rows.filter((r) => r.score == null);
  return scored.concat(unscored);
}

/** Fleet-level aggregates across the scored rows in scope. */
export function buildFleet(rows) {
  const scored = rows.filter((r) => r.hasData);
  const totalFiles = scored.reduce((a, r) => a + (r.totalFiles || 0), 0);
  const weighted = scored.filter((r) => r.delta != null && r.totalFiles);
  const weightSum = weighted.reduce((a, r) => a + r.totalFiles, 0);
  const delta = weightSum
    ? Math.round((weighted.reduce((a, r) => a + r.delta * r.totalFiles, 0) / weightSum) * 10) / 10
    : null;
  const severity = scored.reduce(
    (acc, r) => ({
      critical: acc.critical + (r.severity.critical || 0),
      major: acc.major + (r.severity.major || 0),
      minor: acc.minor + (r.severity.minor || 0),
    }),
    { critical: 0, major: 0, minor: 0 },
  );
  const totalViolations = scored.reduce((a, r) => a + r.totalViolations, 0);
  const totalCompliance = scored.reduce((a, r) => a + r.totalCompliance, 0);
  const checks = totalViolations + totalCompliance;
  const covered = scored.filter((r) => r.coveragePct != null);
  const analyzed = covered.reduce((a, r) => a + (r.analyzedFiles || 0), 0);
  const coverageBase = covered.reduce((a, r) => a + (r.totalFiles || 0), 0);
  // Fleet spread: how uneven the scope is, best project minus worst.
  const byScore = scored.slice().sort((a, b) => b.score - a.score);
  const lead = byScore[0] ?? null;
  const trail = byScore.length > 1 ? byScore[byScore.length - 1] : null;
  return {
    lead,
    trail,
    spread: lead && trail
      ? Math.round((lead.score - trail.score) * 10) / 10
      : null,
    count: rows.length,
    scoredCount: scored.length,
    totalFiles,
    score: mean(scored.map((r) => r.score)),
    delta,
    severity,
    totalViolations,
    totalCompliance,
    checks,
    passPct: checks ? Math.round((totalCompliance / checks) * 100) : null,
    coveragePct: coverageBase ? Math.round((analyzed / coverageBase) * 100) : null,
    staleCount: rows.filter((r) => r.stale).length,
  };
}
