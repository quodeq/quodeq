import {
  TAU, scoreRGB, seedHash, seededRng, gradeToScore, mkParticles,
  mkBackgroundStars, NEUTRAL_SCORE,
} from '../core/galaxyCore.js';
import {
  computeClusterPositions, buildMSTLines, applyRepulsionAndRecenter,
  buildSharedFileConnections, computeMaxExtent,
} from './galaxyViewLayout.js';
import { t } from '../../../../strings/index.js';

// Midpoint of a 0..1 RNG sample: centres a jitter on zero, and flips an
// orbit's direction for half the particles.
const RNG_MIDPOINT = 0.5;

// Scene geometry, in world units. Radii and orbit distances grow with the
// square root of a node's finding count, so one huge dimension widens the
// layout instead of swamping it. `dimParticle` is the dot that stands in
// for a principle while the camera is still at dimension level.
const LAYOUT = Object.freeze({
  dimRadiusBasePx: 3, dimRadiusPerRootFinding: 0.4, dimRingJitterSpanPx: 40,
  clusterSpreadFraction: 0.5, clusterBaseSpreadFraction: 0.3,
  clusterCentreMultiplier: 1.8, clusterSpreadPerDimPx: 12,
  starDistFractionMin: 0.3, starDistFractionRange: 0.45, starDistMinPx: 40,
  prinRadiusBasePx: 6, prinRadiusPerRootFinding: 1.5,
  prinOrbitMinPx: 25, prinOrbitSpanPx: 35, prinOrbitJitterPx: 5,
  dimParticleOrbitBasePx: 12, dimParticleOrbitPerRootFinding: 1.5,
  dimParticleSpeedMin: 0.02, dimParticleSpeedRange: 0.05,
  dimParticleSizeBasePx: 0.8, dimParticleSizePerRootFinding: 0.15,
  dimParticleEccentricityBase: 0.9, dimParticleEccentricityRange: 0.1,
});

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
  // A finite numeric score -- including 0 -- is a real score. Checking
  // `if (rawScore)` first would treat 0 as absent and fall through to the
  // grade/ratio chain below, inconsistent with buildDimStar/
  // updateSceneLiveData, which already keep a 0 overallScore as-is.
  const parsed = parseFloat(rawScore);
  if (Number.isFinite(parsed)) return parsed;
  if (grade) return gradeToScore(grade);
  const total = violationCount + complianceCount;
  return total > 0 ? (complianceCount / total) * 10 : NEUTRAL_SCORE;
}

export const CONSTELLATION_LABELS = {
  builtin: t('map.constellationBuiltin'), quodeq: t('map.constellationQuodeq'), community: t('map.constellationCommunity'), custom: t('map.constellationCustom'), _default: '',
};

/** Group dimensions by standard type, returning the groups and whether they warrant constellations. */
function groupDimensionsByType(dimensions, standardTypes) {
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

  return { dimGroups, groupKeys, useConstellations };
}

/** One dimension's star object, shared shape between the constellation and single-group layouts. */
function buildDimStar(dim, extra) {
  const totalV = dim.totals?.violationCount || dim.violations?.length || 0;
  const totalC = dim.totals?.complianceCount || dim.compliance?.length || 0;
  const parsedScore = parseFloat(dim.overallScore);
  const score = Number.isFinite(parsedScore) ? parsedScore : NEUTRAL_SCORE;
  const radius = LAYOUT.dimRadiusBasePx + Math.sqrt(totalV + totalC) * LAYOUT.dimRadiusPerRootFinding;
  return {
    name: dim.dimension || 'Unknown',
    score, radius,
    violations: totalV, compliance: totalC,
    col: scoreRGB(score),
    x: 0, y: 0,
    principleCount: 0,
    _raw: dim,
    ...extra,
  };
}

// Seeded organic layout — scattered but balanced.
function buildConstellationLayout({ dimGroups, groupKeys, spread, baseClusterSpread, rng }) {
  const stars = [];
  const constellations = [];
  let globalIdx = 0;
  const clusterPositions = computeClusterPositions(groupKeys);

  groupKeys.forEach((type, gi) => {
    const [px, py] = clusterPositions[gi];
    const clusterCx = px * spread * LAYOUT.clusterCentreMultiplier;
    const clusterCy = py * spread * LAYOUT.clusterCentreMultiplier;
    const groupDims = dimGroups[type];
    const clusterSpread = baseClusterSpread + groupDims.length * LAYOUT.clusterSpreadPerDimPx;
    const startIdx = globalIdx;

    const clRng = seededRng(seedHash('cl:' + type));
    const phaseOffset = clRng() * TAU;
    groupDims.forEach((dim) => {
      const n2 = groupDims.length;
      const a = phaseOffset + clRng() * TAU;
      const distVar = LAYOUT.starDistFractionMin + clRng() * LAYOUT.starDistFractionRange;
      const dist = n2 === 1 ? 0 : Math.max(clusterSpread * distVar, LAYOUT.starDistMinPx);
      stars.push(buildDimStar(dim, {
        ba: 0, j: 0,
        _clusterCx: clusterCx, _clusterCy: clusterCy,
        _ox: Math.cos(a) * dist, _oy: Math.sin(a) * dist,
        pp: rng() * TAU,
      }));
      globalIdx++;
    });

    const clusterStars = stars.slice(startIdx);
    const lines = buildMSTLines(clusterStars, startIdx);
    applyRepulsionAndRecenter(clusterStars);

    constellations.push({ type, label: CONSTELLATION_LABELS[type] || type, cx: clusterCx, cy: clusterCy, spread: clusterSpread, lines });
  });

  return { stars, constellations };
}

// Single group — seeded circular layout.
function buildSingleGroupLayout(dimensions, rng) {
  return dimensions.map((dim, i) => buildDimStar(dim, {
    ba: (i / dimensions.length) * TAU - Math.PI / 2,
    j: (rng() - RNG_MIDPOINT) * LAYOUT.dimRingJitterSpanPx,
    _clusterCx: 0, _clusterCy: 0, _ox: 0, _oy: 0,
    pp: rng() * TAU,
  }));
}

/** Level 1: principles per dimension. */
function buildPrinciples(dimensions) {
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
      const radius = LAYOUT.prinRadiusBasePx + Math.sqrt(pv + pc) * LAYOUT.prinRadiusPerRootFinding;
      const sev = countSeverities(p.violations);
      return {
        name: p.name,
        grade: p.grade,
        score: pScore,
        rawScore: p.score,
        violations: pv, compliance: pc,
        radius, col: scoreRGB(pScore),
        ba: (pi / (prinList.length || 1)) * TAU - Math.PI / 2,
        od: LAYOUT.prinOrbitMinPx + (pi / (prinList.length || 1)) * LAYOUT.prinOrbitSpanPx + pRng() * LAYOUT.prinOrbitJitterPx,
        pp: pRng() * TAU,
        ...sev,
        x: 0, y: 0,
        particles: mkParticles(sev.critical, sev.major, sev.minor, radius),
        _rawViolations: p.violations,
        _rawCompliance: p.compliance,
        dimParticle: {
          col: scoreRGB(pScore),
          or: LAYOUT.dimParticleOrbitBasePx + Math.sqrt(pv + pc) * LAYOUT.dimParticleOrbitPerRootFinding,
          os: (LAYOUT.dimParticleSpeedMin + pRng() * LAYOUT.dimParticleSpeedRange) * (pRng() > RNG_MIDPOINT ? 1 : -1),
          op: pRng() * TAU,
          sz: LAYOUT.dimParticleSizeBasePx + Math.sqrt(pv + pc) * LAYOUT.dimParticleSizePerRootFinding,
          ec: LAYOUT.dimParticleEccentricityBase + pRng() * LAYOUT.dimParticleEccentricityRange,
          tp: pRng() * TAU,
        },
      };
    });
  });
  return principles;
}

export function buildScene(dimensions, W, H, standardTypes) {
  const dimFingerprint = dimensions.map(d => d.dimension || '').sort().join('|');
  const rng = seededRng(seedHash('galaxy:' + dimFingerprint));

  const { dimGroups, groupKeys, useConstellations } = groupDimensionsByType(dimensions, standardTypes);

  const spread = Math.min(W, H) * LAYOUT.clusterSpreadFraction;
  const baseClusterSpread = Math.min(W, H) * LAYOUT.clusterBaseSpreadFraction;

  const { stars, constellations } = useConstellations
    ? buildConstellationLayout({ dimGroups, groupKeys, spread, baseClusterSpread, rng })
    : { stars: buildSingleGroupLayout(dimensions, rng), constellations: [] };

  const principles = buildPrinciples(dimensions);
  stars.forEach((s, i) => { s.principleCount = (principles[i] || []).length; });

  const connections = buildSharedFileConnections(dimensions);
  const bg = mkBackgroundStars(seededRng(seedHash('bg:' + dimFingerprint)));
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
    const parsedScore = parseFloat(dim.overallScore);
    const score = Number.isFinite(parsedScore) ? parsedScore : NEUTRAL_SCORE;
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
