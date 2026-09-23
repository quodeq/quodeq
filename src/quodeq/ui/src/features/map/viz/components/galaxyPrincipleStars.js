/**
 * The principle level of the galaxy scene: how a dimension's findings are
 * grouped into principles, how a principle's score is derived when the
 * backend did not supply one, and the orbit each principle star takes around
 * its dimension. Split out of galaxyViewScene.js, which owns the dimension
 * and cluster level and calls into this one.
 */
import {
  TAU, scoreRGB, seedHash, seededRng, gradeToScore, mkParticles,
  NEUTRAL_SCORE, RNG_MIDPOINT,
} from '../core/galaxyCore.js';
import { SEVERITY } from '../../../../vocab/severity.js';

// Principle-level geometry, in world units. Radii and orbit distances grow
// with the square root of a principle's finding count, so one huge principle
// widens the orbit instead of swamping it. `dimParticle` is the dot that
// stands in for a principle while the camera is still at dimension level.
const LAYOUT = Object.freeze({
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
    if (v.severity === SEVERITY.CRITICAL) critical++;
    else if (v.severity === SEVERITY.MAJOR) major++;
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

/**
 * One principle star per principle, per dimension, keyed by the dimension's
 * index in `dimensions`. Each dimension gets its own seeded RNG so adding a
 * dimension does not reshuffle the orbits of the others.
 * @param {Array} dimensions - accumulated per-dimension scores and findings.
 * @returns {Object<number, Array>} dimension index -> its principle stars.
 */
export function buildPrinciples(dimensions) {
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
