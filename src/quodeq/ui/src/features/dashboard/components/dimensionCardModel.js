/** Pure filter/selection logic for DimensionCard's severity/principle/file filters. */

export const SEVERITY_OPTIONS = ['critical', 'major', 'minor', 'unknown'];

export function toggleInList(list, value) {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

export function computePrincipleOptions(dimension) {
  if (!dimension) return [];
  const names = new Set();
  (dimension.principles || []).forEach((p) => names.add(p.name));
  (dimension.violations || []).forEach((v) => { if (v.principle) names.add(v.principle); });
  return Array.from(names).filter(Boolean).sort((a, b) => a.localeCompare(b));
}

export function filterViolations(dimension, selectedSeverities, selectedPrinciples, fileFilter) {
  if (!dimension) return [];
  return (dimension.violations || []).filter((v) => {
    if (selectedSeverities.length > 0 && !selectedSeverities.includes(v.severity || 'unknown')) return false;
    if (selectedPrinciples.length > 0 && !selectedPrinciples.includes(v.principle || '')) return false;
    const normalizedFilter = fileFilter.trim().toLowerCase();
    if (normalizedFilter && !String(v.file || '').toLowerCase().includes(normalizedFilter)) return false;
    return true;
  });
}
