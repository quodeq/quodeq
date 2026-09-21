import { useState } from 'react';
import { LowConfidenceToggle } from '../../../components/LowConfidenceToggle.jsx';
import { isLowConfidence } from '../../../models/runRules.js';

// The rule lives in models/runRules.js; re-exported here so existing
// importers (FileDetailPage) keep their path.
export { isLowConfidence };

export default function LowConfidenceGroup({ violations, renderViolation }) {
  const [expanded, setExpanded] = useState(false);
  if (!violations || violations.length === 0) return null;
  const count = violations.length;
  return (
    <div className="low-confidence-group">
      <LowConfidenceToggle count={count} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
      {expanded && (
        <div className="vlive-violations-group">
          {violations.map((v, idx) => renderViolation(v, idx))}
        </div>
      )}
    </div>
  );
}
