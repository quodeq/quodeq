import { t } from '../../../../strings/index.js';
import { SEVERITY } from '../../../../vocab/severity.js';

// The overlay's fixed styling, hoisted out of the JSX: one object per element
// for the whole module instead of a fresh one on every panel render, and each
// property readable on its own line.
const PANEL_STYLE = {
  position: 'absolute',
  top: 12,
  right: 16,
  background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)',
  border: '1px solid var(--color-border)',
  borderRadius: 10,
  padding: '12px 18px',
  fontSize: 12,
  zIndex: 2,
  backdropFilter: 'blur(8px)',
  minWidth: 160,
};
const TITLE_STYLE = { fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 };
const ROW_STYLE = { display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0' };
const HINT_STYLE = {
  marginTop: 8,
  color: 'var(--color-text-muted)',
  fontSize: 11,
  fontStyle: 'italic',
  opacity: 0.6,
};
const DETAIL_BUTTON_STYLE = {
  marginTop: 10,
  width: '100%',
  padding: '6px 12px',
  background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)',
  border: '1px solid var(--color-border)',
  borderRadius: 6,
  color: 'var(--color-text)',
  fontSize: 11,
  cursor: 'pointer',
  transition: 'all 0.2s',
};
const DETAIL_BUTTON_HOVER_BG = 'color-mix(in srgb, var(--color-accent) 35%, transparent)';

/** Presentational component for the level info panel overlay */
export function LevelInfoPanel({ levelInfo }) {
  if (!levelInfo) return null;
  return (
    <div style={PANEL_STYLE}>
      <div style={TITLE_STYLE}>{levelInfo.title}</div>
      {levelInfo.lines.map((l, i) => (
        <div key={i} style={{ ...ROW_STYLE, color: l.color || 'var(--color-text-muted)' }}>
          <span>{l.label}</span>
          <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
        </div>
      ))}
      {levelInfo.hint && (
        <div style={HINT_STYLE}>{levelInfo.hint}</div>
      )}
      {levelInfo.detailAction && (
        <button
          type="button"
          onClick={levelInfo.detailAction}
          style={DETAIL_BUTTON_STYLE}
          onMouseEnter={e => { e.target.style.background = DETAIL_BUTTON_HOVER_BG; }}
          onMouseLeave={e => { e.target.style.background = DETAIL_BUTTON_STYLE.background; }}
        >{t('map.viewDetails')}</button>
      )}
    </div>
  );
}

/** Shared critical/major/minor line-items, omitting zero counts. */
function buildSevLines(sev) {
  const lines = [];
  if (sev.critical > 0) lines.push({ label: t('map.critical'), value: sev.critical, color: 'var(--color-sev-critical-text)' });
  if (sev.major > 0) lines.push({ label: t('map.major'), value: sev.major, color: 'var(--color-sev-major-text)' });
  if (sev.minor > 0) lines.push({ label: t('map.minor'), value: sev.minor, color: 'var(--color-sev-minor-text)' });
  return lines;
}

/** Depth 0: the whole system, or the active cluster if one is selected. */
function computeSystemLevelInfo(scene, nav, projectName) {
  const clusterStars = nav.clusterCx != null
    ? scene.stars.filter(s => s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy)
    : scene.stars;
  const clusterCon = nav.clusterCx != null
    ? (scene.constellations || []).find(c => c.cx === nav.clusterCx && c.cy === nav.clusterCy)
    : null;
  // One pass over the cluster for every figure (score, violations,
  // compliance, per-severity counts) rather than a reduce per figure.
  let totalV = 0, totalC = 0, totalScore = 0;
  const sevCounts = { critical: 0, major: 0, minor: 0 };
  for (const s of clusterStars) {
    totalV += s.violations;
    totalC += s.compliance;
    totalScore += s.score;
    for (const v of s._raw?.violations || []) {
      const sev = v.severity || SEVERITY.MINOR;
      if (sevCounts[sev] != null) sevCounts[sev]++;
    }
  }
  const avgScore = clusterStars.length > 0 ? totalScore / clusterStars.length : 0;
  const lines = [
    { label: t('map.score'), value: avgScore.toFixed(1) },
    { label: t('map.dimensions'), value: clusterStars.length },
    { label: t('map.violations'), value: totalV },
  ];
  if (totalV > 0) lines.push(...buildSevLines(sevCounts));
  lines.push({ label: t('map.compliance'), value: totalC });
  return {
    title: clusterCon?.label || (projectName ? t('map.projectSystemNamed', { project: projectName }) : t('map.projectSystem')),
    lines, hint: t('map.clickDimension'), detailAction: null,
  };
}

/** Depth 1: one dimension. */
function computeDimensionLevelInfo(scene, nav, navRef, onNavigate) {
  const dim = scene.stars?.[nav.dim];
  if (!dim) return null;
  const prins = scene.principles[nav.dim] || [];
  const rawDim = dim._raw;
  const dimSev = { critical: 0, major: 0, minor: 0 };
  (rawDim?.violations || []).forEach(v => {
    const sev = v.severity || SEVERITY.MINOR;
    if (dimSev[sev] != null) dimSev[sev]++;
  });
  const dimLines = [
    { label: t('map.score'), value: dim.score.toFixed(1) },
    { label: t('map.principles'), value: prins.length },
    { label: t('map.violations'), value: dim.violations },
  ];
  if (dim.violations > 0) dimLines.push(...buildSevLines(dimSev));
  dimLines.push({ label: t('map.compliance'), value: dim.compliance });
  return {
    title: dim.name, lines: dimLines, hint: t('map.clickPrinciple'),
    detailAction: () => {
      const d = scene.stars[navRef.current.dim]?._raw;
      if (!d) return;
      onNavigate?.('explorer', { dimension: d.dimension, runId: d.fromRunId, dateLabel: d.fromDateLabel, fromProject: d.fromProject, sourceTab: 'map' });
    },
  };
}

/** Depth 2: one principle within a dimension. */
function computePrincipleLevelInfo(scene, nav, navRef, onNavigate) {
  const prin = scene.principles?.[nav.dim]?.[nav.prin];
  if (!prin) return null;
  const prinLines = [
    { label: t('map.score'), value: prin.score.toFixed(1) },
    { label: t('map.violations'), value: prin.violations },
  ];
  if (prin.violations > 0) {
    prinLines.push(...buildSevLines({ critical: prin.critical, major: prin.major, minor: prin.minor }));
  }
  prinLines.push({ label: t('map.compliance'), value: prin.compliance });
  return {
    title: prin.name, lines: prinLines, hint: null,
    detailAction: () => {
      const p = scene.principles[navRef.current.dim]?.[navRef.current.prin];
      const d = scene.stars[navRef.current.dim];
      if (!p || !d) return;
      onNavigate?.('evalprinciple', {
        evalPrincipal: {
          principle: p.name,
          score: p.rawScore || (p.score != null ? p.score.toFixed(1) : null),
          grade: p.grade,
          dimension: d.name,
          // Carry the originating run id so PrincipleDetail's dismiss POST
          // sends a real run_id — without it the backend can't rescore and
          // the dismissed entry never lands on the Dismissed tab.
          runId: d._raw?.fromRunId || '',
          principleData: { name: p.name, grade: p.grade, violations: p._rawViolations, compliance: p._rawCompliance },
          dimViolations: p._rawViolations,
          dimCompliance: p._rawCompliance,
        },
        sourceTab: 'map',
      });
    },
  };
}

/**
 * Compute the level info panel data for the current navigation depth.
 *
 * @param {object} scene - The scene built by buildScene
 * @param {object} nav - Current navigation state { depth, dim, prin, clusterCx, clusterCy }
 * @param {string} projectName - Project name for display
 * @param {Function} onNavigate - Navigation callback
 * @param {React.MutableRefObject} navRef - Ref to live nav state (for detail actions)
 * @returns {object|null} { title, lines, hint, detailAction }
 */
export function computeLevelInfo(scene, nav, projectName, onNavigate, navRef) {
  if (!scene) return null;
  if (nav.depth === 0) return computeSystemLevelInfo(scene, nav, projectName);
  if (nav.depth === 1 && nav.dim !== null) return computeDimensionLevelInfo(scene, nav, navRef, onNavigate);
  if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) return computePrincipleLevelInfo(scene, nav, navRef, onNavigate);
  return null;
}

/**
 * The constellation crumb, when navigation sits inside one. The cluster is
 * the explicit nav selection, else the selected star's own cluster.
 */
function clusterCrumb(scene, nav, star) {
  const cx = nav.clusterCx ?? star?._clusterCx;
  const cy = nav.clusterCy ?? star?._clusterCy;
  if (cx == null) return null;
  const con = (scene?.constellations || []).find(c => c.cx === cx && c.cy === cy);
  if (!con) return null;
  return { label: con.label, depth: 0, action: () => { nav.clusterCx = con.cx; nav.clusterCy = con.cy; } };
}

/**
 * Build breadcrumb items for current navigation state.
 *
 * @param {object} scene - The scene data
 * @param {object} nav - Current navigation state
 * @param {string} projectName - Project name for display
 * @returns {Array} Breadcrumb parts with { label, depth, action? }
 */
export function buildBreadcrumb(scene, nav, projectName) {
  const rootLabel = projectName
    ? t('map.projectSystemNamed', { project: projectName })
    : t('map.breadcrumbSystem');
  const parts = [{ label: rootLabel, depth: 0, action: () => { nav.clusterCx = null; nav.clusterCy = null; } }];
  const star = nav.dim !== null ? scene?.stars[nav.dim] : null;
  const cluster = clusterCrumb(scene, nav, star);
  if (cluster) parts.push(cluster);
  if (nav.dim !== null && scene) parts.push({ label: scene.stars[nav.dim].name, depth: 1 });
  if (nav.prin !== null && scene) parts.push({ label: scene.principles[nav.dim][nav.prin].name, depth: 2 });
  return parts;
}
