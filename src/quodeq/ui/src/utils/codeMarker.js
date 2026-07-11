/**
 * Highlight marker used to flag the violation lines inside a code-context
 * block.
 *
 * The analysis backend (src/quodeq/analysis/mcp/enrichment.py) prefixes every
 * highlighted line with `">>> "` — three chevrons plus a single space. The
 * space is a separator between the marker and the code, NOT part of the source
 * line, so it must be stripped along with the chevrons. Stripping only the
 * three chevrons leaves the highlighted line rendered one space too far to the
 * right, misaligned from the surrounding context.
 */
export const HIGHLIGHT_MARKER = '>>> ';

/** True when `line` carries the highlight marker. */
export function isHighlightedLine(line) {
  return typeof line === 'string' && line.startsWith('>>>');
}

/**
 * Remove the highlight marker (and its single-space separator) from a line,
 * recovering the original source text with its indentation intact. Lines
 * without the marker are returned unchanged.
 */
export function stripHighlightMarker(line) {
  if (typeof line !== 'string') return line;
  if (line.startsWith(HIGHLIGHT_MARKER)) return line.slice(HIGHLIGHT_MARKER.length);
  // Defensive: a bare ">>>" with no separator space — drop only the chevrons
  // so no source character is lost.
  if (line.startsWith('>>>')) return line.slice(3);
  return line;
}
