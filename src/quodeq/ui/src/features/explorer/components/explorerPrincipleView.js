import { countBySeverity } from '../../../utils/severity.js';

// Grade the backend writes when a principle had no evidence to judge; the
// radial dashes those points instead of plotting a score.
const INSUFFICIENT_GRADE = 'insufficient';

/** Radial chart points: one per principle, score null (dashed on the
 * radial) when the grade carries no real evidence. */
export function buildRadialPrinciples(principleGrades) {
  return (principleGrades || []).map((pg) => {
    const score = parseFloat(pg.score);
    const hasEvidence = (pg.grade || '').toLowerCase() !== INSUFFICIENT_GRADE
      && !Number.isNaN(score);
    return { name: pg.principle, score: hasEvidence ? score : null, hasEvidence };
  });
}

/**
 * Enrich each principleGrade with the per-principle counts that
 * DimensionGaugeCard expects: total violations, compliance count, and a
 * severity histogram. The data comes from the same evalData we already
 * have — no extra API call.
 */
export function buildEnrichedPrinciples(principleGrades, allViolations, complianceByPrinciple) {
  const violationsByPrinciple = new Map();
  for (const v of allViolations || []) {
    const key = v.principle;
    if (!key) continue;
    if (!violationsByPrinciple.has(key)) violationsByPrinciple.set(key, []);
    // has()+set() above guarantee an entry here: one lookup into a local,
    // not a re-derefed call expression (matches dimensionHeatGridModel.js).
    const list = violationsByPrinciple.get(key);
    list.push(v);
  }
  return (principleGrades || []).map((pg) => {
    const vs = violationsByPrinciple.get(pg.principle) || [];
    const severity = countBySeverity(vs);
    const compliance = complianceByPrinciple?.get?.(pg.principle) || [];
    return {
      ...pg,
      violationCount: vs.length,
      complianceCount: compliance.length,
      severity,
    };
  });
}
