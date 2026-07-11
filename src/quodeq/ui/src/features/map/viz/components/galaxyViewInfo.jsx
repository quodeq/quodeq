import React from 'react';

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
        >View Details</button>
      )}
    </div>
  );
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
  if (nav.depth === 0) {
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
      { label: 'Score', value: avgScore.toFixed(1) },
      { label: 'Dimensions', value: clusterStars.length },
      { label: 'Violations', value: totalV },
    ];
    if (totalV > 0) {
      if (sevCounts.critical > 0) lines.push({ label: 'Critical', value: sevCounts.critical, color: 'var(--color-sev-critical-text)' });
      if (sevCounts.major > 0) lines.push({ label: 'Major', value: sevCounts.major, color: 'var(--color-sev-major-text)' });
      if (sevCounts.minor > 0) lines.push({ label: 'Minor', value: sevCounts.minor, color: 'var(--color-sev-minor-text)' });
    }
    lines.push({ label: 'Compliance', value: totalC });
    return {
      title: clusterCon?.label || (projectName ? `${projectName} System` : 'Project System'),
      lines, hint: 'Click a dimension to explore', detailAction: null,
    };
  }

  if (nav.depth === 1 && nav.dim !== null) {
    const dim = scene.stars[nav.dim];
    const prins = scene.principles[nav.dim] || [];
    const rawDim = dim._raw;
    const dimSev = { critical: 0, major: 0, minor: 0 };
    (rawDim?.violations || []).forEach(v => {
      const sev = v.severity || 'minor';
      if (dimSev[sev] != null) dimSev[sev]++;
    });
    const dimLines = [
      { label: 'Score', value: dim.score.toFixed(1) },
      { label: 'Principles', value: prins.length },
      { label: 'Violations', value: dim.violations },
    ];
    if (dim.violations > 0) {
      if (dimSev.critical > 0) dimLines.push({ label: 'Critical', value: dimSev.critical, color: 'var(--color-sev-critical-text)' });
      if (dimSev.major > 0) dimLines.push({ label: 'Major', value: dimSev.major, color: 'var(--color-sev-major-text)' });
      if (dimSev.minor > 0) dimLines.push({ label: 'Minor', value: dimSev.minor, color: 'var(--color-sev-minor-text)' });
    }
    dimLines.push({ label: 'Compliance', value: dim.compliance });
    return {
      title: dim.name, lines: dimLines, hint: 'Click a principle to explore',
      detailAction: () => {
        const d = scene.stars[navRef.current.dim]?._raw;
        if (!d) return;
        onNavigate?.('explorer', { dimension: d.dimension, runId: d.fromRunId, dateLabel: d.fromDateLabel, fromProject: d.fromProject, sourceTab: 'map' });
      },
    };
  }

  if (nav.depth === 2 && nav.dim !== null && nav.prin !== null) {
    const prin = scene.principles[nav.dim][nav.prin];
    const prinLines = [
      { label: 'Score', value: prin.score.toFixed(1) },
      { label: 'Violations', value: prin.violations },
    ];
    if (prin.violations > 0) {
      if (prin.critical > 0) prinLines.push({ label: 'Critical', value: prin.critical, color: 'var(--color-sev-critical-text)' });
      if (prin.major > 0) prinLines.push({ label: 'Major', value: prin.major, color: 'var(--color-sev-major-text)' });
      if (prin.minor > 0) prinLines.push({ label: 'Minor', value: prin.minor, color: 'var(--color-sev-minor-text)' });
    }
    prinLines.push({ label: 'Compliance', value: prin.compliance });
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
  const parts = [{ label: projectName ? `${projectName} System` : 'System', depth: 0, action: () => { nav.clusterCx = null; nav.clusterCy = null; } }];
  const star = nav.dim !== null ? scene?.stars[nav.dim] : null;
  const clusterCx = nav.clusterCx ?? star?._clusterCx;
  const clusterCy = nav.clusterCy ?? star?._clusterCy;
  const clusterCon = clusterCx != null ? (scene?.constellations || []).find(c => c.cx === clusterCx && c.cy === clusterCy) : null;
  if (clusterCon) parts.push({ label: clusterCon.label, depth: 0, action: () => { nav.clusterCx = clusterCon.cx; nav.clusterCy = clusterCon.cy; } });
  if (nav.dim !== null && scene) parts.push({ label: scene.stars[nav.dim].name, depth: 1 });
  if (nav.prin !== null && scene) parts.push({ label: scene.principles[nav.dim][nav.prin].name, depth: 2 });
  return parts;
}
