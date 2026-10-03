function groupByPrinciple(findings) {
  const map = new Map();
  for (const f of findings || []) {
    if (!map.has(f.principle)) map.set(f.principle, []);
    // has()+set() above guarantee an entry here: one lookup into a local,
    // not a re-derefed call expression (matches dimensionHeatGridModel.js).
    const list = map.get(f.principle);
    list.push(f);
  }
  return map;
}

/**
 * Groups an evaluation's compliance findings by principle name, so a
 * principle view can read its own entries in one lookup.
 *
 * @returns {Map<string, Array<object>>}
 */
export function computeComplianceByPrinciple(evalData) {
  return groupByPrinciple(evalData?.compliance);
}

/**
 * Builds a lookup that assembles the full principle record (score, grade,
 * violations, compliance, run context) for one principle name.
 *
 * The per-principle indexes are built once here, so the returned function is
 * cheap to call for every row in a list. `dimViolations` are the eval's flat
 * violations for the principle: a stored eval's principles carry no rows of
 * their own (the flat rows are the ones whose deferred detail can be
 * refilled), while a markdown eval's principle rows are read by the page
 * when present.
 *
 * @returns {(principleId: string) => object}
 */
export function buildEvalPrincipalFn(evalData, complianceByPrinciple, project, runId, dateLabel = '') {
  const principlesByName = new Map((evalData.principles || []).map((p) => [p.name, p]));
  const gradesByPrinciple = new Map((evalData.principleGrades || []).map((p) => [p.principle, p]));
  const violationsByPrinciple = groupByPrinciple(evalData.violations);
  return function buildEvalPrincipal(principleId) {
    const principleData = principlesByName.get(principleId);
    const pg = gradesByPrinciple.get(principleId);
    return {
      principle: principleId, score: pg?.score ?? null, grade: pg?.grade ?? null,
      dimension: evalData.dimension || '',
      project: project || '', runId: runId || '', dateLabel: dateLabel || '',
      principleData, dimViolations: violationsByPrinciple.get(principleId) || [],
      dimCompliance: complianceByPrinciple.get(principleId) || [],
    };
  };
}
