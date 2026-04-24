/**
 * SectionLabel — subtle uppercase section divider.
 *
 * By default, renders a clean uppercase label (matches the DIMENSIONS /
 * TOP_FINDINGS / SCORE_HISTORY banner style). Pass `marker="//"` (or `"--"`,
 * `"#"`) to get the legacy comment-prefixed look. An explicit empty string
 * suppresses the marker element entirely.
 *
 * @param {object} props
 * @param {React.ReactNode} props.children
 * @param {string} [props.marker]
 */
export default function SectionLabel({ children, marker }) {
  const hasMarker = marker != null && marker !== '';
  return (
    <div className="term-section-label">
      {hasMarker && (
        <span className="term-section-label__marker" aria-hidden="true">{marker}</span>
      )}
      <span className="term-section-label__text">{children}</span>
    </div>
  );
}
