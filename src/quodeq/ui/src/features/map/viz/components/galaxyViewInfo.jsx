import React from 'react';
import { t } from '../../../../strings/index.js';

/** Presentational component for the level info panel overlay */
export function LevelInfoPanel({ levelInfo }) {
  if (!levelInfo) return null;
  return (
    <div style={{ position: 'absolute', top: 12, right: 16, background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)', border: '1px solid var(--color-border)', borderRadius: 10, padding: '12px 18px', fontSize: 12, zIndex: 2, backdropFilter: 'blur(8px)', minWidth: 160 }}>
      <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 }}>{levelInfo.title}</div>
      {levelInfo.lines.map((l, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: l.color || 'var(--color-text-muted)' }}>
          <span>{l.label}</span>
          <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
        </div>
      ))}
      {levelInfo.hint && (
        <div style={{ marginTop: 8, color: 'var(--color-text-muted)', fontSize: 11, fontStyle: 'italic', opacity: 0.6 }}>{levelInfo.hint}</div>
      )}
      {levelInfo.detailAction && (
        <button
          type="button"
          onClick={levelInfo.detailAction}
          style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
          onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
          onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
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
  const totalV = clusterStars.reduce((s, d) => s + d.violations, 0);
  const totalC = clusterStars.reduce((s, d) => s + d.compliance, 0);
  const avgScore = clusterStars.length > 0 ? clusterStars.reduce((s, d) => s + d.score, 0) / clusterStars.length : 0;
  const sevCounts = { critical: 0, major: 0, minor: 0 };
  clusterStars.forEach(s => {
    (s._raw?.violations || []).forEach(v => {
      const sev = v.severity || 'minor';
      if (sevCounts[sev] != null) sevCounts[sev]++;
    });
  });
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
  const dim = scene.stars[nav.dim];
  const prins = scene.principles[nav.dim] || [];
  const rawDim = dim._raw;
  const dimSev = { critical: 0, major: 0, minor: 0 };
  (rawDim?.violations || []).forEach(v => {
    const sev = v.severity || 'minor';
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
  const prin = scene.principles[nav.dim][nav.prin];
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
 * Build breadcrumb items for current navigation state.
 *
 * @param {object} scene - The scene data
 * @param {object} nav - Current navigation state
 * @param {string} projectName - Project name for display
 * @returns {Array} Breadcrumb parts with { label, depth, action? }
 */
export function buildBreadcrumb(scene, nav, projectName) {
  const parts = [{ label: projectName ? t('map.projectSystemNamed', { project: projectName }) : t('map.breadcrumbSystem'), depth: 0, action: () => { nav.clusterCx = null; nav.clusterCy = null; } }];
  const star = nav.dim !== null ? scene?.stars[nav.dim] : null;
  const clusterCx = nav.clusterCx ?? star?._clusterCx;
  const clusterCy = nav.clusterCy ?? star?._clusterCy;
  const clusterCon = clusterCx != null ? (scene?.constellations || []).find(c => c.cx === clusterCx && c.cy === clusterCy) : null;
  if (clusterCon) parts.push({ label: clusterCon.label, depth: 0, action: () => { nav.clusterCx = clusterCon.cx; nav.clusterCy = clusterCon.cy; } });
  if (nav.dim !== null && scene) parts.push({ label: scene.stars[nav.dim].name, depth: 1 });
  if (nav.prin !== null && scene) parts.push({ label: scene.principles[nav.dim][nav.prin].name, depth: 2 });
  return parts;
}
