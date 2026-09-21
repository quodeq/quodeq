import { headerRowKey } from './findingListRows.js';

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
    if (item.kind === 'sev-header' || item.kind === 'compliance-header') return ROW_HEIGHT_PX.HEADER;
    if (item.kind === 'low-conf-toggle') return ROW_HEIGHT_PX.HEADER;
    return ROW_HEIGHT_PX.VIOLATION;
  };
}

export function itemKey(items) {
  return (i) => {
    const item = items[i];
    if (!item) return i;
    const header = headerRowKey(item);
    if (header) return header;
    if (item.kind === 'low-conf-toggle') return 'h-lowconf';
    if (item.kind === 'violation') {
      return `v-${item.v.dimension || ''}:${item.v.file || ''}:${item.v.line ?? ''}:${item.v.principle || ''}:${item.v.title || ''}`;
    }
    if (item.kind === 'low-conf-row') {
      return `lc-${item.v.dimension || ''}:${item.v.file || ''}:${item.v.line ?? ''}:${item.v.principle || ''}:${item.v.title || ''}`;
    }
    if (item.kind === 'compliance') {
      return `c-${item.c.dimension || ''}:${item.c.file || ''}:${item.c.line ?? ''}:${item.c.principle || ''}`;
    }
    return i;
  };
}
