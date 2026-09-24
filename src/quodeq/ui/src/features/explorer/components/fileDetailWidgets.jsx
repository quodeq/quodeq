import { headerRowKey, ROW_KIND } from './findingListRows.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';

// Re-exported so the file-detail pane keeps importing its row widgets from
// one module.
export { LowConfidenceToggle } from '../../../components/LowConfidenceToggle.jsx';

export function GroupHeader({ title, count }) {
  return (
    <div className="violation-group-header">
      <span className="violation-group-title" role="heading" aria-level={3}>{title}</span>
      <span className="violation-group-count">{count}</span>
    </div>
  );
}

// Virtual-list row estimates for the file detail pane. The severity and
// compliance headers and the low-confidence toggle are all one header row;
// FALLBACK covers an item the list has not materialised yet.
const ROW_HEIGHT_PX = Object.freeze({ FALLBACK: 140, HEADER: 36, VIOLATION: 160 });

export function estimateItemSize(items) {
  return (i) => {
    const item = items[i];
    if (!item) return ROW_HEIGHT_PX.FALLBACK;
    if (item.kind === ROW_KIND.SEV_HEADER || item.kind === ROW_KIND.COMPLIANCE_HEADER) return ROW_HEIGHT_PX.HEADER;
    if (item.kind === ROW_KIND.LOW_CONF_TOGGLE) return ROW_HEIGHT_PX.HEADER;
    return ROW_HEIGHT_PX.VIOLATION;
  };
}

/** Identity of one finding row: dimension, file, line, principle and title. */
function findingKey(prefix, v) {
  return `${prefix}-${v.dimension || ''}:${v.file || ''}:${v.line ?? ''}:${v.principle || ''}:${v.title || ''}`;
}

/** Identity of one compliance row. No title: compliances do not carry one. */
function complianceKey(c) {
  return `c-${c.dimension || ''}:${c.file || ''}:${c.line ?? ''}:${c.principle || ''}`;
}

export function itemKey(items) {
  return (i) => {
    const item = items[i];
    if (!item) return i;
    const header = headerRowKey(item);
    if (header) return header;
    if (item.kind === ROW_KIND.LOW_CONF_TOGGLE) return 'h-lowconf';
    if (item.kind === FINDING_TYPE.VIOLATION) return findingKey('v', item.v);
    if (item.kind === ROW_KIND.LOW_CONF_ROW) return findingKey('lc', item.v);
    if (item.kind === FINDING_TYPE.COMPLIANCE) return complianceKey(item.c);
    return i;
  };
}
