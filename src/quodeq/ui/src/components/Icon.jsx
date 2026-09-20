/**
 * The shared <svg> shell every inline icon draws into.
 *
 * The app's icons are all 24x24-viewBox line drawings in currentColor, and
 * they are decorative: the button or link around them carries the accessible
 * name, so the svg itself is always aria-hidden. Repeating that attribute set
 * per icon meant a change (a stroke weight, the hidden flag) had to be made in
 * every copy, so it lives here once.
 *
 * `size` is the rendered box in px. Any other svg attribute passed in
 * overrides the default — `fill="currentColor"` for a solid glyph, or
 * `strokeLinecap={null}` / `strokeLinejoin={null}` for the few icons that
 * deliberately keep the SVG defaults (butt caps, mitre joins).
 */

const ICON_VIEWBOX = '0 0 24 24';

const BASE_ICON_ATTRS = {
  viewBox: ICON_VIEWBOX,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: '2',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true',
};

export default function Icon({ size, children, ...overrides }) {
  return (
    <svg width={size} height={size} {...BASE_ICON_ATTRS} {...overrides}>
      {children}
    </svg>
  );
}
