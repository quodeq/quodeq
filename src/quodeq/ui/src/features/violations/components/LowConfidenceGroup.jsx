import { useState } from 'react';

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
        <span className="violation-group-title">Low confidence</span>
        <span className="violation-group-count">{count}</span>
        <span className="low-confidence-group-hint">
          {expanded ? 'Hide' : 'Show'} likely false positives
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
