import { useState } from 'react';
import { t } from '../../../strings/index.js';

const LOW_CONFIDENCE_THRESHOLD = 50;

export function isLowConfidence(violation) {
  return typeof violation?.confidence === 'number' && violation.confidence < LOW_CONFIDENCE_THRESHOLD;
}

export default function LowConfidenceGroup({ violations, renderViolation }) {
  const [expanded, setExpanded] = useState(false);
  if (!violations || violations.length === 0) return null;
  const count = violations.length;
  return (
    <div className="low-confidence-group">
      <button
        type="button"
        className="violation-group-header low-confidence-group-header"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
      >
        <span className="violation-group-title">{t('violations.lowConfidence')}</span>
        <span className="violation-group-count">{count}</span>
        <span className="low-confidence-group-hint">
          {expanded ? t('violations.hideLikelyFp') : t('violations.showLikelyFp')}
        </span>
      </button>
      {expanded && (
        <div className="vlive-violations-group">
          {violations.map((v, idx) => renderViolation(v, idx))}
        </div>
      )}
    </div>
  );
}
