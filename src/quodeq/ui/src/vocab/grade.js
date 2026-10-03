// Mirror of src/quodeq/core/scoring/constants.py:Grade, best first.
//
// GRADE_LADDER here is the display order of those five labels. It is NOT the
// Python GRADE_LADDER, which is the qualitative-mode ladder and carries two
// labels ("Developing", "Proficient") the UI never receives.
export const GRADE = Object.freeze({
  EXEMPLARY: 'Exemplary', GOOD: 'Good', ADEQUATE: 'Adequate', POOR: 'Poor', INSUFFICIENT: 'Insufficient',
});
export const GRADE_LADDER = Object.freeze(Object.values(GRADE));
