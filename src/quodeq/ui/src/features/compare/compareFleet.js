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
import { PROJECT_SOURCE } from '../../vocab/projectSource.js';
import { SORT_DIR } from '../../vocab/sortDirection.js';
import { roundOneDecimal } from '../../utils/rounding.js';
import { SCORE_SCALE_MAX, PERCENT } from '../../constants.js';
import { projectId } from '../../utils/projectIdentity.js';
import { emptySeverityCounts, sumSeverityTallies } from '../../utils/severity.js';

// consequenceLevel's return values, in ascending severity. CompareFleetView
// and useCompareScopeActions both compare against CLEAR to decide whether a
// row is worth surfacing in the attention strip / "select flagged" action.
export const CONSEQUENCE_LEVEL = Object.freeze({
  SEVERE: 'severe', ELEVATED: 'elevated', WATCH: 'watch', CLEAR: 'clear',
});

// Consequence thresholds. The score scales as
// (10 - score) * log10(files + 10) * staleness, i.e. roughly 0..45 across
// realistic projects; these cuts put a failing large stale project in SEVERE
// and a healthy project of any size in CLEAR.
const SEVERE_AT = 18;
const ELEVATED_AT = 11;
const WATCH_AT = 6;
const STALE_FACTOR = 1.35;
// Added to the file count before log10 so log10(files + offset) is always
// >= 1: a 0-file (or tiny) project's size weight never drops below 1, so its
// consequence score never shrinks under the raw (score-scale - score) gap.
const FILE_COUNT_LOG_OFFSET = 10;

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
      severity: d.totals?.severity || emptySeverityCounts(),
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
 * Identity and origin. Remote (shared-repo) rows carry the prefixed
 * fleet-unique key as `id`, while `sourceId` is the raw project id every API
 * call and source-switching navigation needs. Local rows keep sourceId === id.
 */
function _rowIdentity(project, id) {
  return {
    id,
    source: project.source === PROJECT_SOURCE.SHARED ? PROJECT_SOURCE.SHARED : PROJECT_SOURCE.LOCAL,
    sourceId: project.sourceId || id,
    remote: project.source === PROJECT_SOURCE.SHARED,
    name: project.displayName || project.name || id,
  };
}

/** File counts and the share of them the last run got through. */
function _rowCoverage(project) {
  const totalFiles = project.totalFiles ?? project.filesCount ?? null;
  const analyzedFiles = project.analyzedFiles ?? null;
  return {
    lang: topLanguage(project.languageStats),
    totalFiles,
    analyzedFiles,
    coveragePct: totalFiles && analyzedFiles != null
      ? Math.round((analyzedFiles / totalFiles) * PERCENT)
      : null,
  };
}

/** Score, grade, trend and violation counts off the compare summary. */
function _rowScores(score, s, trend) {
  return {
    score,
    grade: s?.overallGrade ?? null,
    delta: trend.delta,
    lastDelta: trend.lastDelta,
    spark: trend.spark,
    severity: s?.severity || emptySeverityCounts(),
    totalViolations: s?.totalViolations ?? 0,
    totalCompliance: s?.totalCompliance ?? 0,
  };
}

/** When the project last ran, and whether that leaves the row stale. */
function _rowFreshness(project, summary, now) {
  const lastISO = summary?.lastRun?.dateISO || project.latestDate || null;
  const commitsSince = summary?.commitsSinceLastRun ?? null;
  const ageDays = lastISO ? daysBetween(lastISO, now) : null;
  return { lastISO, stale: _deriveStaleness(commitsSince, ageDays), commitsSince };
}

/** Whether the row has arrived yet and whether it has anything to show. */
function _rowStatus(project, summary, score) {
  return {
    hasRuns: (project.runsCount ?? 0) > 0 || (summary?.runsCount ?? 0) > 0,
    loaded: summary !== undefined,
    hasData: score != null,
    dims: _buildRowDims(summary),
  };
}

/**
 * One fleet-table row: a Project model joined with its compare summary.
 * `summary` may be undefined while the per-project query is in flight.
 */
export function buildRow(project, summary, now) {
  const id = projectId(project);
  const s = summary?.summary || null;
  const score = s?.numericAverage ?? null;
  return {
    ..._rowIdentity(project, id),
    ..._rowCoverage(project),
    ..._rowScores(score, s, trendDelta(summary?.trend, now)),
    ..._rowFreshness(project, summary, now),
    ..._rowStatus(project, summary, score),
  };
}

/** Higher = more deserving of attention. 0 for rows without a score. */
export function consequenceOf(row) {
  if (row.score == null) return 0;
  const sizeWeight = Math.log10((row.totalFiles ?? 0) + FILE_COUNT_LOG_OFFSET);
  const staleness = row.stale ? STALE_FACTOR : 1;
  return (SCORE_SCALE_MAX - row.score) * sizeWeight * staleness;
}

export function consequenceLevel(value) {
  if (value >= SEVERE_AT) return CONSEQUENCE_LEVEL.SEVERE;
  if (value >= ELEVATED_AT) return CONSEQUENCE_LEVEL.ELEVATED;
  if (value >= WATCH_AT) return CONSEQUENCE_LEVEL.WATCH;
  return CONSEQUENCE_LEVEL.CLEAR;
}

/**
 * Score ordering with a direction toggle. Rows without a score always sink
 * to the bottom, whichever direction is active — an unevaluated project is
 * not "the worst project".
 */
export function sortRows(rows, direction = SORT_DIR.DESC) {
  const scored = rows.filter((r) => r.score != null)
    .sort((a, b) => (direction === SORT_DIR.ASC ? a.score - b.score : b.score - a.score));
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
    ? roundOneDecimal(weighted.reduce((a, r) => a + r.delta * r.totalFiles, 0) / weightSum)
    : null;
  const severity = sumSeverityTallies(scored);
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
      ? roundOneDecimal(lead.score - trail.score)
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
    passPct: checks ? Math.round((totalCompliance / checks) * PERCENT) : null,
    coveragePct: coverageBase ? Math.round((analyzed / coverageBase) * PERCENT) : null,
    staleCount: rows.filter((r) => r.stale).length,
  };
}
