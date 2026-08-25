/**
 * Pure view-model builders for the Compare tab.
 *
 * Everything here is plain data-in/data-out so the fleet aggregation,
 * consequence ranking and dimension drill-down can be unit tested without
 * mounting React. Inputs are the Project models from /api/projects plus one
 * compare-summary payload per project (see services/compare.py); nothing in
 * this module fetches.
 */

// A project counts as stale when its newest run is older than this. Mirrors
// the "grade measured on old data" idea from the design: the number shown is
// real but the codebase has moved since.
export const STALE_AFTER_DAYS = 7;

// Delta window: the design's "7w" column. Baseline is the newest run at or
// before the window start, so the delta reads "change over the last 7 weeks"
// even when runs are unevenly spaced.
export const DELTA_WINDOW_DAYS = 49;

// Consequence thresholds. The score scales as
// (10 - score) * log10(files + 10) * staleness, i.e. roughly 0..45 across
// realistic projects; these cuts put a failing large stale project in SEVERE
// and a healthy project of any size in CLEAR.
const SEVERE_AT = 18;
const ELEVATED_AT = 11;
const WATCH_AT = 6;
const STALE_FACTOR = 1.35;

/** "7.2", "7.2/10", "7.2/10 Good" or 7.2 → number, else null. */
export function parseScore10(value) {
  if (value == null) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const m = String(value).match(/^(\d+(?:\.\d+)?)/);
  return m ? parseFloat(m[1]) : null;
}

/** Case-insensitive identity for dimension/principle names across projects. */
export function nameKey(name) {
  return String(name || '').trim().toLowerCase();
}

function daysBetween(isoA, isoB) {
  const a = new Date(isoA).getTime();
  const b = new Date(isoB).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return (b - a) / 86400000;
}

function sortedByDate(trend) {
  return (trend || [])
    .filter((e) => e && e.dateISO && e.numericAverage != null)
    .slice()
    .sort((a, b) => new Date(a.dateISO) - new Date(b.dateISO));
}

/**
 * Score movement over the delta window plus the sparkline series.
 * `pick` extracts the numeric value from a trend entry (defaults to the
 * accumulated average; the dimension view passes a per-dimension picker).
 *
 * `delta` is the change within the window (null when every run predates it —
 * nothing moved in the last 7 weeks). `lastDelta` is the change between the
 * two most recent runs regardless of age, for a muted fallback display.
 */
export function trendDelta(trend, now, pick = (e) => e.numericAverage) {
  const entries = sortedByDate(trend)
    .map((e) => ({ dateISO: e.dateISO, value: pick(e) }))
    .filter((e) => e.value != null);
  const spark = entries.map((e) => e.value);
  if (entries.length < 2) return { delta: null, lastDelta: null, spark };
  const latest = entries[entries.length - 1];
  const previous = entries[entries.length - 2];
  const lastDelta = Math.round((latest.value - previous.value) * 10) / 10;
  const cutoff = new Date(now).getTime() - DELTA_WINDOW_DAYS * 86400000;
  let baseline = entries[0];
  for (const e of entries) {
    if (new Date(e.dateISO).getTime() <= cutoff) baseline = e;
    else break;
  }
  if (baseline === latest) return { delta: null, lastDelta, spark };
  return { delta: Math.round((latest.value - baseline.value) * 10) / 10, lastDelta, spark };
}

function topLanguage(languageStats) {
  if (!languageStats || typeof languageStats !== 'object') return null;
  let best = null;
  for (const [lang, count] of Object.entries(languageStats)) {
    if (!best || count > best.count) best = { lang, count };
  }
  return best?.lang ?? null;
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
  const stale = ageDays != null && ageDays > STALE_AFTER_DAYS;
  const totalFiles = project.totalFiles ?? project.filesCount ?? null;
  const analyzedFiles = project.analyzedFiles ?? null;
  const { delta, lastDelta, spark } = trendDelta(summary?.trend, now);
  const dims = (summary?.dimensions || [])
    .map((d) => ({
      key: nameKey(d.dimension),
      label: String(d.dimension || '').toLowerCase(),
      score: parseScore10(d.overallScore),
      grade: d.overallGrade ?? null,
      violations: d.totals?.violationCount ?? 0,
      severity: d.totals?.severity || { critical: 0, major: 0, minor: 0 },
      principles: (d.principles || []).map((p) => ({
        key: nameKey(p.principle || p.name),
        label: String(p.principle || p.name || '').toLowerCase(),
        score: parseScore10(p.score),
      })),
    }))
    .filter((d) => d.key);
  return {
    id,
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

function mean(values) {
  const xs = values.filter((v) => v != null);
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
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
  return {
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

/** Union of dimensions across scope, each with fleet stats + per-project scores. */
export function buildDimensionsBoard(rows, now, summariesById) {
  const byKey = new Map();
  for (const row of rows) {
    for (const dim of row.dims) {
      let entry = byKey.get(dim.key);
      if (!entry) {
        entry = { key: dim.key, label: dim.label, perProject: [], violations: 0, deltas: [] };
        byKey.set(dim.key, entry);
      }
      entry.perProject.push({ id: row.id, name: row.name, score: dim.score, row, dim });
      entry.violations += dim.violations;
      const summary = summariesById?.[row.id];
      if (summary) {
        const { delta } = trendDelta(summary.trend, now, (e) => {
          const detail = (e.dimensionDetails || []).find((d) => nameKey(d.dimension) === dim.key);
          return detail ? parseScore10(detail.score) : null;
        });
        if (delta != null) entry.deltas.push(delta);
      }
    }
  }
  return Array.from(byKey.values())
    .map((entry) => ({
      key: entry.key,
      label: entry.label,
      avg: mean(entry.perProject.map((p) => p.score)),
      delta: entry.deltas.length
        ? Math.round(mean(entry.deltas) * 10) / 10
        : null,
      violations: entry.violations,
      perProject: entry.perProject
        .filter((p) => p.score != null)
        .sort((a, b) => b.score - a.score),
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/**
 * Top-N rows by consequence with machine-readable reasons the component
 * turns into copy. Reasons: worst-dimension, declining, stale, coverage-gap.
 */
export function buildAttention(rows, limit = 3) {
  return rows
    .filter((r) => r.hasData)
    .map((row) => {
      const value = consequenceOf(row);
      const worst = row.dims
        .filter((d) => d.score != null)
        .reduce((acc, d) => (acc == null || d.score < acc.score ? d : acc), null);
      const reasons = [];
      if (worst) reasons.push({ type: 'worstDim', dim: worst.label, score: worst.score });
      if (row.delta != null && row.delta <= -0.3) reasons.push({ type: 'declining', delta: row.delta });
      if (row.stale) reasons.push({ type: 'stale' });
      if (row.coveragePct != null && row.coveragePct < 80) {
        reasons.push({ type: 'coverage', pct: row.coveragePct });
      }
      return { row, value, level: consequenceLevel(value), worstDim: worst?.key ?? null, reasons };
    })
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

/** Drill-down model for one dimension across the scope. */
export function buildDimensionView(dimensionKey, rows, now, summariesById) {
  const holders = rows
    .map((row) => ({ row, dim: row.dims.find((d) => d.key === dimensionKey) }))
    .filter((h) => h.dim && h.dim.score != null);
  if (!holders.length) return null;
  const label = holders[0].dim.label;
  const standings = holders
    .map(({ row, dim }) => {
      const summary = summariesById?.[row.id];
      const { delta, lastDelta } = trendDelta(summary?.trend, now, (e) => {
        const detail = (e.dimensionDetails || []).find((d) => nameKey(d.dimension) === dimensionKey);
        return detail ? parseScore10(detail.score) : null;
      });
      return { row, score: dim.score, delta, lastDelta, violations: dim.violations, severity: dim.severity, principles: dim.principles };
    })
    .sort((a, b) => b.score - a.score);
  const lead = standings[0];
  const trail = standings[standings.length - 1];
  const severity = standings.reduce(
    (acc, s) => ({
      critical: acc.critical + (s.severity.critical || 0),
      major: acc.major + (s.severity.major || 0),
      minor: acc.minor + (s.severity.minor || 0),
    }),
    { critical: 0, major: 0, minor: 0 },
  );

  const principleKeys = new Map();
  for (const { row, principles } of standings.map((s) => ({ row: s.row, principles: s.principles }))) {
    for (const p of principles) {
      if (p.score == null) continue;
      let entry = principleKeys.get(p.key);
      if (!entry) {
        entry = { key: p.key, label: p.label, perProject: [] };
        principleKeys.set(p.key, entry);
      }
      entry.perProject.push({ id: row.id, name: row.name, score: p.score });
    }
  }
  const principles = Array.from(principleKeys.values())
    .map((entry) => {
      const ranked = entry.perProject.slice().sort((a, b) => b.score - a.score);
      return {
        key: entry.key,
        label: entry.label,
        avg: mean(ranked.map((p) => p.score)),
        lead: ranked[0] ?? null,
        trail: ranked.length > 1 ? ranked[ranked.length - 1] : null,
        perProject: ranked,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
  const weakest = principles.reduce(
    (acc, p) => (acc == null || (p.avg ?? 11) < (acc.avg ?? 11) ? p : acc),
    null,
  );

  return {
    key: dimensionKey,
    label,
    avg: mean(standings.map((s) => s.score)),
    delta: (() => {
      const ds = standings.map((s) => s.delta).filter((d) => d != null);
      return ds.length ? Math.round(mean(ds) * 10) / 10 : null;
    })(),
    spread: lead && trail && lead !== trail
      ? Math.round((lead.score - trail.score) * 10) / 10
      : null,
    lead,
    trail,
    violations: standings.reduce((a, s) => a + s.violations, 0),
    severity,
    principles,
    weakest,
    standings,
  };
}
