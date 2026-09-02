/**
 * Single-dimension drill-down builders for the Compare tab. Split out of
 * compareModel.js — see compareModel.js for the module-level docs.
 */
import { nameKey, parseScore10, trendDelta, mean } from './compareModel.js';

/**
 * Outliers inside ONE dimension, for its scoped needs-attention strip.
 * Two signals: a principle where one project sits far under the rest
 * (1.5+ under the next score, or below 4.5 outright), and a standing
 * that dropped hard inside the 30-day window. An empty result means the
 * strip does not render at all. Returns EVERYTHING that qualifies,
 * weight-sorted; the view caps the strip at 3 behind an expand toggle.
 */
export function buildDimensionAttention(view) {
  if (!view) return [];
  const items = [];
  for (const p of view.principles) {
    const by = p.perProject
      .filter((x) => x.score != null)
      .slice()
      .sort((a, b) => a.score - b.score);
    if (by.length < 2) continue;
    const worst = by[0];
    const gap = Math.round((by[1].score - worst.score) * 10) / 10;
    if (gap < 1.5 && worst.score >= 4.5) continue;
    items.push({
      kind: 'outlier',
      name: worst.name,
      level: worst.score < 4.5 || gap >= 2.5 ? 'elevated' : 'watch',
      principleLabel: p.label,
      score: worst.score,
      gap: gap >= 1.5 ? gap : null,
      cell: worst,
      weight: (10 - worst.score) + gap,
    });
  }
  for (const s of view.standings) {
    if (s.delta == null || s.delta > -0.5) continue;
    items.push({
      kind: 'drop',
      name: s.row.name,
      level: s.delta <= -1 ? 'elevated' : 'watch',
      delta: s.delta,
      row: s.row,
      weight: Math.abs(s.delta) * 2 + (10 - (s.score ?? 10)),
    });
  }
  return items.sort((a, b) => b.weight - a.weight);
}

function _buildStandings(holders, dimensionKey, now, summariesById) {
  return holders
    .map(({ row, dim }) => {
      const summary = summariesById?.[row.id];
      const { delta, lastDelta } = trendDelta(summary?.trend, now, (e) => {
        const detail = (e.dimensionDetails || []).find((d) => nameKey(d.dimension) === dimensionKey);
        return detail ? parseScore10(detail.score) : null;
      });
      return {
        row,
        score: dim.score,
        delta,
        lastDelta,
        violations: dim.violations,
        compliance: dim.compliance,
        severity: dim.severity,
        principles: dim.principles,
        // Cross-project navigation targets for this project's dimension.
        runId: dim.fromRunId,
        dimName: dim.name,
        dateLabel: dim.fromDateLabel,
      };
    })
    .sort((a, b) => b.score - a.score);
}

function _summarizeSeverity(standings) {
  return standings.reduce(
    (acc, s) => ({
      critical: acc.critical + (s.severity.critical || 0),
      major: acc.major + (s.severity.major || 0),
      minor: acc.minor + (s.severity.minor || 0),
    }),
    { critical: 0, major: 0, minor: 0 },
  );
}

function _buildPrincipleBoard(standings) {
  const principleKeys = new Map();
  for (const s of standings) {
    for (const p of s.principles) {
      if (p.score == null) continue;
      let entry = principleKeys.get(p.key);
      if (!entry) {
        entry = { key: p.key, label: p.label, perProject: [] };
        principleKeys.set(p.key, entry);
      }
      entry.perProject.push({
        id: s.row.id,
        name: s.row.name,
        score: p.score,
        // Everything a click needs to open THIS project's view of THIS
        // principle: the run the number came from and the raw spellings.
        // Remote rows can't deep-link into local project pages; the click
        // handler falls back to opening the shared project instead.
        remote: s.row.remote ?? false,
        principle: p.name,
        runId: s.runId,
        dimName: s.dimName,
        dateLabel: s.dateLabel,
      });
    }
  }
  return Array.from(principleKeys.values())
    .map((entry) => {
      const byScore = entry.perProject.slice().sort((a, b) => b.score - a.score);
      // Bars render in the STANDINGS order, not per-principle rank: the same
      // slot means the same project in every card, and each bar carries its
      // standings rank so it ties back to the numbered list on screen.
      const inStandingsOrder = standings
        .map((s, idx) => {
          const p = entry.perProject.find((x) => x.id === s.row.id);
          return p ? { ...p, rank: idx + 1 } : null;
        })
        .filter(Boolean);
      return {
        key: entry.key,
        label: entry.label,
        avg: mean(byScore.map((p) => p.score)),
        lead: byScore[0] ?? null,
        trail: byScore.length > 1 ? byScore[byScore.length - 1] : null,
        perProject: inStandingsOrder,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** Drill-down model for one dimension across the scope. */
export function buildDimensionView(dimensionKey, rows, now, summariesById) {
  const holders = rows
    .map((row) => ({ row, dim: row.dims.find((d) => d.key === dimensionKey) }))
    .filter((h) => h.dim && h.dim.score != null);
  if (!holders.length) return null;
  const label = holders[0].dim.label;
  const standings = _buildStandings(holders, dimensionKey, now, summariesById);
  const lead = standings[0];
  const trail = standings[standings.length - 1];
  const severity = _summarizeSeverity(standings);
  const principles = _buildPrincipleBoard(standings);
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
