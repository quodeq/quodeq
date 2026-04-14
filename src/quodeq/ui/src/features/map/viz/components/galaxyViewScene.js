import {
  TAU, scoreRGB, seedHash, seededRng, gradeToScore, mkParticles,
} from '../core/galaxyCore.js';
import {
  computeClusterPositions, buildMSTLines, applyRepulsionAndRecenter,
  buildSharedFileConnections, computeMaxExtent,
} from './galaxyViewLayout.js';

/** Group violations and compliance by principle name, returning { [principleName]: { violations, compliance } } */
export function groupByPrinciple(dim) {
  const groups = {};
  for (const v of (dim.violations || [])) {
    const key = v.principle || '(ungrouped)';
    if (!groups[key]) groups[key] = { violations: [], compliance: [] };
    groups[key].violations.push(v);
  }
  for (const c of (dim.compliance || [])) {
    const key = c.principle || '(ungrouped)';
    if (!groups[key]) groups[key] = { violations: [], compliance: [] };
    groups[key].compliance.push(c);
  }
  return groups;
}

/** Build a lookup from principle name to { grade, score } from dim.principles array */
export function buildGradeLookup(dim) {
  const lookup = {};
  for (const p of (dim.principles || [])) {
    const key = p.name || p.principle || '';
    if (key) lookup[key] = { grade: p.grade, score: p.score };
  }
  return lookup;
}

/** Count severity levels from a violations array, returning { critical, major, minor } */
export function countSeverities(violations) {
  let critical = 0, major = 0, minor = 0;
  for (const v of violations) {
    if (v.severity === 'critical') critical++;
    else if (v.severity === 'major') major++;
    else minor++;
  }
  return { critical, major, minor };
}

/** Compute a principle's score from raw data, grade, or violation ratio */
export function computePrincipleScore(rawScore, grade, violationCount, complianceCount) {
  if (rawScore) return parseFloat(rawScore);
  if (grade) return gradeToScore(grade);
  const total = violationCount + complianceCount;
  return total > 0 ? (complianceCount / total) * 10 : 5;
}

export const CONSTELLATION_LABELS = {
  builtin: 'ISO Standards', quodeq: 'Quodeq Standards', community: 'Community Standards', custom: 'Custom Standards', _default: '',
};

export function buildScene(dimensions, W, H, standardTypes) {
  const dimFingerprint = dimensions.map(d => d.dimension || '').sort().join('|');
  const rng = seededRng(seedHash('galaxy:' + dimFingerprint));

  // Group dimensions by standard type
  const dimGroups = {};
  dimensions.forEach(dim => {
    const id = (dim.dimension || '').toLowerCase();
    const type = standardTypes[id] || '_default';
    if (!dimGroups[type]) dimGroups[type] = [];
    dimGroups[type].push(dim);
  });

  const groupKeys = Object.keys(dimGroups).filter(k => k !== '_default');
  if (dimGroups._default) groupKeys.push('_default');
  const useConstellations = groupKeys.length > 1 || (groupKeys.length === 1 && groupKeys[0] !== '_default');

  const stars = [];
  const constellations = [];
  let globalIdx = 0;

  const spread = Math.min(W, H) * 0.5;
  const baseClusterSpread = Math.min(W, H) * 0.3;

  if (useConstellations) {
    const clusterPositions = computeClusterPositions(groupKeys);

    groupKeys.forEach((type, gi) => {
      const [px, py] = clusterPositions[gi];
      const clusterCx = px * spread * 1.8;
      const clusterCy = py * spread * 1.8;
      const groupDims = dimGroups[type];
      const clusterSpread = baseClusterSpread + groupDims.length * 12;

      const startIdx = globalIdx;

      // Seeded organic layout — scattered but balanced
      const clRng = seededRng(seedHash('cl:' + type));
      const phaseOffset = clRng() * TAU;
      groupDims.forEach((dim) => {
        const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
        const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
        const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
        const radius = 3 + Math.sqrt(totalV + totalC) * 0.4;
        const n2 = groupDims.length;
        const a = phaseOffset + clRng() * TAU;
        const distVar = 0.3 + clRng() * 0.45;
        const dist = n2 === 1 ? 0 : Math.max(clusterSpread * distVar, 40);
        stars.push({
          name: dim.dimension || 'Unknown',
          score, radius,
          violations: totalV, compliance: totalC,
          col: scoreRGB(score),
          ba: 0, j: 0,
          _clusterCx: clusterCx, _clusterCy: clusterCy,
          _ox: Math.cos(a) * dist, _oy: Math.sin(a) * dist,
          pp: rng() * TAU,
          x: 0, y: 0,
          principleCount: 0,
          _raw: dim,
        });
        globalIdx++;
      });

      const clusterStars = stars.slice(startIdx);
      const lines = buildMSTLines(clusterStars, startIdx);
      applyRepulsionAndRecenter(clusterStars);

      constellations.push({ type, label: CONSTELLATION_LABELS[type] || type, cx: clusterCx, cy: clusterCy, spread: clusterSpread, lines });
    });
  } else {
    // Single group — seeded circular layout
    dimensions.forEach((dim, i) => {
      const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
      const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
      const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
      const radius = 3 + Math.sqrt(totalV + totalC) * 0.4;
      stars.push({
        name: dim.dimension || 'Unknown',
        score, radius,
        violations: totalV, compliance: totalC,
        col: scoreRGB(score),
        ba: (i / dimensions.length) * TAU - Math.PI / 2,
        j: (rng() - 0.5) * 40,
        _clusterCx: 0, _clusterCy: 0, _ox: 0, _oy: 0,
        pp: rng() * TAU,
        x: 0, y: 0,
        principleCount: 0,
        _raw: dim,
      });
    });
  }

  // Level 1: Principles per dimension
  const principles = {};
  dimensions.forEach((dim, di) => {
    const groups = groupByPrinciple(dim);
    const gradeLookup = buildGradeLookup(dim);
    const prinList = Object.entries(groups).map(([name, g]) => ({
      name,
      grade: gradeLookup[name]?.grade || null,
      score: gradeLookup[name]?.score || null,
      violations: g.violations,
      compliance: g.compliance,
    }));
    const pRng = seededRng(seedHash('prin:' + (dim.dimension || di)));
    principles[di] = prinList.map((p, pi) => {
      const pv = p.violations.length;
      const pc = p.compliance.length;
      const pScore = computePrincipleScore(p.score, p.grade, pv, pc);
      const radius = 6 + Math.sqrt(pv + pc) * 1.5;
      const sev = countSeverities(p.violations);
      return {
        name: p.name,
        grade: p.grade,
        score: pScore,
        rawScore: p.score,
        violations: pv, compliance: pc,
        radius, col: scoreRGB(pScore),
        ba: (pi / (prinList.length || 1)) * TAU - Math.PI / 2,
        od: 25 + (pi / (prinList.length || 1)) * 35 + pRng() * 5,
        pp: pRng() * TAU,
        ...sev,
        x: 0, y: 0,
        particles: mkParticles(sev.critical, sev.major, sev.minor, radius),
        _rawViolations: p.violations,
        _rawCompliance: p.compliance,
        dimParticle: {
          col: scoreRGB(pScore),
          or: 12 + Math.sqrt(pv + pc) * 1.5,
          os: (0.02 + pRng() * 0.05) * (pRng() > 0.5 ? 1 : -1),
          op: pRng() * TAU,
          sz: 0.8 + Math.sqrt(pv + pc) * 0.15,
          ec: 0.9 + pRng() * 0.1,
          tp: pRng() * TAU,
        },
      };
    });
  });

  stars.forEach((s, i) => { s.principleCount = (principles[i] || []).length; });

  const connections = buildSharedFileConnections(dimensions);

  const bgRng = seededRng(seedHash('bg:' + dimFingerprint));
  const bg = Array.from({ length: 120 }, () => ({
    x: bgRng(), y: bgRng(),
    sz: bgRng() * 1.2,
    tw: bgRng() * TAU,
    sp: 0.3 + bgRng() * 0.7,
  }));

  const _maxExtent = computeMaxExtent(stars, constellations);

  return { stars, principles, connections, constellations, bg, _maxExtent };
}

/**
 * Update live data (scores, violations, particles) on an existing scene without regenerating layout.
 */
export function updateSceneLiveData(scene, dimensions) {
  dimensions.forEach((dim, di) => {
    const star = scene.stars[di];
    if (!star) return;
    const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
    const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
    const score = dim.overallScore ? parseFloat(dim.overallScore) : 5;
    star.violations = totalV;
    star.compliance = totalC;
    star.score = score;
    star.col = scoreRGB(score);
    star._raw = dim;

    const groups = groupByPrinciple(dim);
    const gradeLookup = buildGradeLookup(dim);

    (scene.principles[di] || []).forEach(prin => {
      const g = groups[prin.name];
      if (!g) { prin.violations = 0; prin.compliance = 0; prin._rawViolations = []; prin._rawCompliance = []; prin.particles = []; return; }
      const pv = g.violations.length;
      const pc = g.compliance.length;
      const gl = gradeLookup[prin.name];
      const pScore = computePrincipleScore(gl?.score, gl?.grade, pv, pc);
      const sev = countSeverities(g.violations);
      prin.violations = pv;
      prin.compliance = pc;
      prin.score = pScore;
      prin.rawScore = gl?.score || null;
      prin.grade = gl?.grade || null;
      prin.col = scoreRGB(pScore);
      prin._rawViolations = g.violations;
      prin._rawCompliance = g.compliance;
      if (sev.critical !== prin.critical || sev.major !== prin.major || sev.minor !== prin.minor) {
        prin.particles = mkParticles(sev.critical, sev.major, sev.minor, prin.radius);
      }
      prin.critical = sev.critical; prin.major = sev.major; prin.minor = sev.minor;
    });
  });
  scene.stars.forEach((s, i) => { s.principleCount = (scene.principles[i] || []).length; });
}
