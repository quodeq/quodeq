import { t } from '../../../strings/index.js';

export function GroupHeader({ title, count }) {
  return (
    <div className="violation-group-header">
      <span className="violation-group-title">{title}</span>
      <span className="violation-group-count">{count}</span>
    </div>
  );
}

export function LowConfidenceToggle({ count, expanded, onToggle }) {
  return (
    <button
      type="button"
      className="violation-group-header low-confidence-group-header"
      aria-expanded={expanded}
      onClick={onToggle}
    >
      <span className="violation-group-title">{t('violations.lowConfidence')}</span>
      <span className="violation-group-count">{count}</span>
      <span className="low-confidence-group-hint">
        {expanded ? t('violations.hideLikelyFp') : t('violations.showLikelyFp')}
      </span>
    </button>
  );
}

export function estimateItemSize(items) {
  return (i) => {
    const item = items[i];
    if (!item) return 140;
    if (item.kind === 'sev-header' || item.kind === 'compliance-header') return 36;
    if (item.kind === 'low-conf-toggle') return 36;
    return 160;
  };
}

export function itemKey(items) {
  return (i) => {
    const item = items[i];
    if (!item) return i;
    if (item.kind === 'sev-header') return `h-${item.sev}`;
    if (item.kind === 'compliance-header') return 'h-compliance';
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
