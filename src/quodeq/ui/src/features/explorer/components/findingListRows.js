/**
 * Row identity shared by the Explorer's virtualised finding lists.
 *
 * The file-detail pane and the principle-detail page both interleave severity
 * and compliance headers with their findings, and both need a stable key per
 * row; the header half of that key is the same in each.
 */

/**
 * The virtual-list key for a header row, or null when `item` is not a header.
 *
 * @param {{kind: string, sev?: string}} item
 * @returns {string|null}
 */
export function headerRowKey(item) {
  if (item.kind === 'sev-header') return `h-${item.sev}`;
  if (item.kind === 'compliance-header') return 'h-compliance';
  return null;
}
