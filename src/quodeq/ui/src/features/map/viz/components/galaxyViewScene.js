import {
  TAU, scoreRGB, seedHash, seededRng, mkParticles,
  mkBackgroundStars, NEUTRAL_SCORE, RNG_MIDPOINT,
} from '../core/galaxyCore.js';
import {
  computeClusterPositions, buildMSTLines, applyRepulsionAndRecenter,
  buildSharedFileConnections, computeMaxExtent,
} from './galaxyViewLayout.js';
import {
  groupByPrinciple, buildGradeLookup, countSeverities, computePrincipleScore, buildPrinciples,
} from './galaxyPrincipleStars.js';
import { t } from '../../../../strings/index.js';

// Re-exported: the principle helpers were defined here before the principle
// level moved to its own module, and callers still reach them through the
// scene's surface.
export {
  groupByPrinciple, buildGradeLookup, countSeverities, computePrincipleScore,
} from './galaxyPrincipleStars.js';


// Dimension- and cluster-level geometry, in world units. Radii and spreads
// grow with the square root of a node's finding count, so one huge dimension
// widens the layout instead of swamping it. The principle level carries its
// own tuning in galaxyPrincipleStars.js.
const LAYOUT = Object.freeze({
  dimRadiusBasePx: 3, dimRadiusPerRootFinding: 0.4, dimRingJitterSpanPx: 40,
  clusterSpreadFraction: 0.5, clusterBaseSpreadFraction: 0.3,
  clusterCentreMultiplier: 1.8, clusterSpreadPerDimPx: 12,
  starDistFractionMin: 0.3, starDistFractionRange: 0.45, starDistMinPx: 40,
});

/**
 * A dimension's finding totals and its displayed score.
 *
 * Both the initial star build and the live-data update read the same three
 * numbers off a dimension, with the same fallbacks: totals first, then the
 * raw arrays, and the neutral score when overallScore does not parse.
 */
function dimStarTotals(dim) {
  const violations = dim.totals?.violationCount || dim.violations?.length || 0;
  const compliance = dim.totals?.complianceCount || dim.compliance?.length || 0;
  const parsedScore = parseFloat(dim.overallScore);
  const score = Number.isFinite(parsedScore) ? parsedScore : NEUTRAL_SCORE;
  return { violations, compliance, score };
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
  const { violations: totalV, compliance: totalC, score } = dimStarTotals(dim);
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

// The dimension stars, and the constellations holding them when the
// standards carry types worth grouping by. Both layouts share the scene's
// seeded RNG, so a given set of dimension names always lands the same way.
function buildStarLayout(dimensions, standardTypes, { W, H, rng }) {
  const { dimGroups, groupKeys, useConstellations } = groupDimensionsByType(dimensions, standardTypes);
  if (!useConstellations) {
    return { stars: buildSingleGroupLayout(dimensions, rng), constellations: [] };
  }
  const spread = Math.min(W, H) * LAYOUT.clusterSpreadFraction;
  const baseClusterSpread = Math.min(W, H) * LAYOUT.clusterBaseSpreadFraction;
  return buildConstellationLayout({ dimGroups, groupKeys, spread, baseClusterSpread, rng });
}

/**
 * Lay out the whole galaxy: one cluster per dimension, its principles in
 * orbit, and the background starfield. Positions are seeded from the
 * dimension names, so the same project always renders the same sky.
 * @param {Array} dimensions - accumulated per-dimension scores and findings.
 * @param {number} W - canvas width in px.
 * @param {number} H - canvas height in px.
 * @param {Object} standardTypes - dimension id -> standard type, which decides
 *   whether dimensions are grouped into constellations.
 * @returns {object} the scene: `rootStars`, `bg` and the layout metadata the
 *   draw and camera helpers read.
 */
export function buildScene(dimensions, W, H, standardTypes) {
  const dimFingerprint = dimensions.map(d => d.dimension || '').sort().join('|');
  const rng = seededRng(seedHash('galaxy:' + dimFingerprint));

  const { stars, constellations } = buildStarLayout(dimensions, standardTypes, { W, H, rng });

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
    const { violations: totalV, compliance: totalC, score } = dimStarTotals(dim);
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
