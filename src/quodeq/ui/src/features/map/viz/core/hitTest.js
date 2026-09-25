/**
 * Whether the point (x, y) lies strictly inside the circle of radius `r`
 * centred on (cx, cy). The canvas views hit-test the cursor this way.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} cx
 * @param {number} cy
 * @param {number} r
 * @returns {boolean}
 */
export function withinRadius(x, y, cx, cy, r) {
  const dx = x - cx, dy = y - cy;
  return dx * dx + dy * dy < r * r;
}
