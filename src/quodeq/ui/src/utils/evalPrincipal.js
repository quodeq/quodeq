/**
 * Groups an evaluation's compliance findings by principle name, so a
 * principle view can read its own entries in one lookup.
 *
 * @returns {Map<string, Array<object>>}
 */
export function computeComplianceByPrinciple(evalData) {
  const map = new Map();
  for (const c of (evalData?.compliance || [])) {
    if (!map.has(c.principle)) map.set(c.principle, []);
    map.get(c.principle)?.push(c);
  }
  return map;
}

/**
 * Builds a lookup that assembles the full principle record (score, grade,
 * violations, compliance, run context) for one principle name.
 *
 * The per-principle indexes are built once here, so the returned function is
 * cheap to call for every row in a list.
 *
 * @returns {(principleId: string) => object}
 */
export function buildEvalPrincipalFn(evalData, complianceByPrinciple, project, runId, dateLabel = '') {
  const principlesByName = new Map((evalData.principles || []).map((p) => [p.name, p]));
  const gradesByPrinciple = new Map((evalData.principleGrades || []).map((p) => [p.principle, p]));
  return function buildEvalPrincipal(principleId) {
    const principleData = principlesByName.get(principleId);
    const pg = gradesByPrinciple.get(principleId);
    return {
      principle: principleId, score: pg?.score || null, grade: pg?.grade || null,
      dimension: evalData.dimension || '',
      project: project || '', runId: runId || '', dateLabel: dateLabel || '',
      principleData, dimViolations: principleData?.violations || [],
      dimCompliance: complianceByPrinciple.get(principleId) || [],
    };
  };
}
