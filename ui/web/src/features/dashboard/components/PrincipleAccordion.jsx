// Props: { principle, onViolationClick }
// Expandable accordion showing principle details and its violations list.
// Clicking a violation calls onViolationClick(violation, principle).

import { useState } from 'react';
import { gradeColorClass } from '../../../utils/formatters.js';

export default function PrincipleAccordion({ principle, onViolationClick }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="principle-accordion">
      <button
        className="principle-accordion-header"
        onClick={() => setOpen(!open)}
      >
        <span className={`accordion-chevron ${open ? 'open' : ''}`}>›</span>
        <span className="principle-name">{principle.name}</span>
        <span className={`chip ${gradeColorClass(principle.grade)}`}>{principle.grade}</span>
      </button>

      {open && (
        <div className="principle-accordion-content">
          {principle.compliance?.length > 0 && (
            <div className="principle-section">
              <h4>Compliance Evidence</h4>
              {principle.compliance.map((code, i) => (
                <pre key={i} className="code-snippet compliance">{code}</pre>
              ))}
            </div>
          )}

          {principle.violations?.length > 0 && (
            <div className="principle-section">
              <h4>Violations Found</h4>
              <div className="violation-list">
                {principle.violations.map((v, i) => (
                  <div
                    key={i}
                    className={`violation-row${onViolationClick ? ' clickable' : ''}`}
                    onClick={onViolationClick ? () => onViolationClick(v, principle) : undefined}
                  >
                    <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
                    <span className="violation-row-file">{v.file || '—'}</span>
                    {onViolationClick && <span className="violation-row-arrow">›</span>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {principle.justification && (
            <div className="principle-section">
              <h4>Grade Justification</h4>
              <p>{principle.justification}</p>
            </div>
          )}

          {principle.recommendations?.length > 0 && (
            <div className="principle-section">
              <h4>Recommendations</h4>
              <ol>
                {principle.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ol>
            </div>
          )}

          {principle.metrics && (
            <div className="principle-section metrics-section">
              <h4>Metrics</h4>
              <div className="metrics-grid">
                {principle.metrics.instancesExamined && (
                  <div className="metric">
                    <span className="metric-value">{principle.metrics.instancesExamined}</span>
                    <span className="metric-label">Instances Examined</span>
                  </div>
                )}
                {principle.metrics.complianceRate && (
                  <div className="metric">
                    <span className="metric-value">{principle.metrics.complianceRate}%</span>
                    <span className="metric-label">Compliance Rate</span>
                  </div>
                )}
                {principle.metrics.confidenceLevel && (
                  <div className="metric">
                    <span className="metric-value">{principle.metrics.confidenceLevel}</span>
                    <span className="metric-label">Confidence</span>
                  </div>
                )}
              </div>
              <div className="severity-breakdown">
                <span className="severity-item critical">{principle.metrics.severity?.critical || 0} critical</span>
                <span className="severity-item major">{principle.metrics.severity?.major || 0} major</span>
                <span className="severity-item minor">{principle.metrics.severity?.minor || 0} minor</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
