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

// Rows the virtualizer sizes as a one-line header: the severity and
// compliance section headers and the low-confidence toggle.
const HEADER_ROW_KINDS = new Set([ROW_KIND.SEV_HEADER, ROW_KIND.COMPLIANCE_HEADER, ROW_KIND.LOW_CONF_TOGGLE]);

/**
 * The virtual list's `getItemKey`: headers key themselves, every other row
 * gets `findingKey(item, index)`, and a row not materialised yet keys by index.
 *
 * @param {Array<{kind: string}>} items
 * @param {(item: object, index: number) => string|number} findingKey
 * @returns {(index: number) => string|number}
 */
export function rowKeyGetter(items, findingKey) {
  return (i) => {
    const item = items[i];
    if (!item) return i;
    const header = headerRowKey(item);
    if (header) return header;
    return findingKey(item, i);
  };
}

/**
 * The virtual list's `estimateSize`: `header` for header rows, `row` for
 * finding rows and `missing` for a row not materialised yet.
 *
 * @param {Array<{kind: string}>} items
 * @param {{missing: number, header: number, row: number}} heights
 * @returns {(index: number) => number}
 */
export function rowSizeEstimator(items, { missing, header, row }) {
  return (i) => {
    const item = items[i];
    if (!item) return missing;
    return HEADER_ROW_KINDS.has(item.kind) ? header : row;
  };
}
