// Base/ceiling curve math for the grade-formula preview plot.
//
// Source of truth: quodeq.core.scoring.internals (Python) --
//   - baseCurve mirrors violation_base's formula at internals.py:46
//     (`return 10.0 / (1.0 + params.base_k * wv)`)
//   - ceilingCurve mirrors violation_ceiling's formula at internals.py:77
//     (`return 10.0 - math.log2(1.0 + wv) * params.ceil_scale`)
// These are PREVIEW-ONLY curves (a function of weighted-violations alone,
// ignoring compliance lift/floors); the real score is computed server-side.

/** Base score curve: 10 at wv=0, hyperbolic decay past it. */
export function baseCurve(wv, baseK) {
  return wv === 0 ? 10 : 10 / (1 + baseK * wv);
}

/** Ceiling curve: the maximum achievable score given the violation weight. */
export function ceilingCurve(wv, ceilScale) {
  return wv === 0 ? 10 : 10 - Math.log2(1 + wv) * ceilScale;
}
