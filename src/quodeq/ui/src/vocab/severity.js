// Mirror of src/quodeq/core/types/severity.py.
export const SEVERITY = Object.freeze({ CRITICAL: 'critical', MAJOR: 'major', MINOR: 'minor' });
export const SEVERITY_ORDER = Object.freeze([SEVERITY.CRITICAL, SEVERITY.MAJOR, SEVERITY.MINOR]);
// UI-only sentinel meaning "no severity filter applied". Not a Severity value
// itself, but every severity-filter comparison already imports from this file.
export const SEVERITY_FILTER_ALL = 'all';
