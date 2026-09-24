/**
 * Row identity shared by the Explorer's virtualised finding lists.
 *
 * The file-detail pane and the principle-detail page both interleave severity
 * and compliance headers with their findings, and both need a stable key per
 * row; the header half of that key is the same in each.
 */

// The non-finding row kinds useFileDetailFiltering.js interleaves with
// FINDING_TYPE.VIOLATION/COMPLIANCE rows: FileDetailPage.jsx,
// PrincipleDetailPage.jsx and fileDetailWidgets.jsx all switch on these.
export const ROW_KIND = Object.freeze({
  SEV_HEADER: 'sev-header', COMPLIANCE_HEADER: 'compliance-header',
  LOW_CONF_TOGGLE: 'low-conf-toggle', LOW_CONF_ROW: 'low-conf-row',
});

/**
 * The virtual-list key for a header row, or null when `item` is not a header.
 *
 * @param {{kind: string, sev?: string}} item
 * @returns {string|null}
 */
export function headerRowKey(item) {
  if (item.kind === ROW_KIND.SEV_HEADER) return `h-${item.sev}`;
  if (item.kind === ROW_KIND.COMPLIANCE_HEADER) return 'h-compliance';
  return null;
}
