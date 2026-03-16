// Props: { title, dimension, isSingleFocus }
// Full dimension score card with:
//   - Score display (uses splitScore, gradeColorClass from utils/formatters.js)
//   - Principles accordion (uses PrincipleAccordion from ./PrincipleAccordion.jsx)
//   - Violations summary
//   - Filter controls (selectedSeverities, selectedPrinciples, fileFilter) as internal state
//   - TrendBadge (from components/TrendBadge.jsx)
//   - CopyButton (from components/CopyButton.jsx) that copies a fix plan

import { useState, useMemo } from 'react';
import PrincipleAccordion from './PrincipleAccordion.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CopyButton from '../../../components/CopyButton.jsx';
import { splitScore, gradeColorClass } from '../../../utils/formatters.js';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';

const SEVERITY_OPTIONS = ['critical', 'major', 'minor', 'unknown'];

function toggleInList(list, value) {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

export default function DimensionCard({ title, dimension, isSingleFocus }) {
  const [selectedSeverities, setSelectedSeverities] = useState([]);
  const [selectedPrinciples, setSelectedPrinciples] = useState([]);
  const [fileFilter, setFileFilter] = useState('');

  const principleOptions = useMemo(() => {
    if (!dimension) return [];
    const names = new Set();
    (dimension.principles || []).forEach((p) => names.add(p.name));
    (dimension.violations || []).forEach((v) => { if (v.principle) names.add(v.principle); });
    return Array.from(names).filter(Boolean).sort((a, b) => a.localeCompare(b));
  }, [dimension]);

  const filteredViolations = useMemo(() => {
    if (!dimension) return [];
    return (dimension.violations || []).filter((v) => {
      if (selectedSeverities.length > 0 && !selectedSeverities.includes(v.severity || 'unknown')) {
        return false;
      }
      if (selectedPrinciples.length > 0 && !selectedPrinciples.includes(v.principle || '')) {
        return false;
      }
      const normalizedFilter = fileFilter.trim().toLowerCase();
      if (normalizedFilter && !String(v.file || '').toLowerCase().includes(normalizedFilter)) {
        return false;
      }
      return true;
    });
  }, [dimension, selectedSeverities, selectedPrinciples, fileFilter]);

  const activeFilterCount =
    (selectedSeverities.length > 0 ? 1 : 0) +
    (selectedPrinciples.length > 0 ? 1 : 0) +
    (fileFilter.trim() ? 1 : 0);

  const clearAllFilters = () => {
    setSelectedSeverities([]);
    setSelectedPrinciples([]);
    setFileFilter('');
  };

  const buildFixPlan = () => {
    const dimName = dimension?.dimension || title || 'dimension';
    return buildDimensionPlanFromViolations(dimName, filteredViolations);
  };

  if (!dimension) {
    return (
      <section className="panel dim-card">
        <h3>{title}</h3>
        <p className="dimension-meta">Select a dimension.</p>
      </section>
    );
  }

  const { value: scoreValue, denom: scoreDenom } = splitScore(dimension.overallScore);

  const currScore = parseFloat(dimension.overallScore);
  const prevScore = parseFloat(dimension.previousScore);
  const delta = !isNaN(currScore) && !isNaN(prevScore) ? (currScore - prevScore) : null;

  return (
    <section className={`panel dim-card ${isSingleFocus ? 'full-width' : ''}`}>
      <div className="compare-column-header">
        <div>
          {title && <p className="brand-overline">{title}</p>}
          <h3>{dimension.dimension}</h3>
        </div>
        <span className={`chip ${gradeColorClass(dimension.overallGrade)}`}>
          {dimension.overallGrade || 'No grade'}
        </span>
      </div>

      {dimension.overallScore && (
        <div className="dim-score-row">
          <span className="dim-score-value">{scoreValue}</span>
          {scoreDenom && <span className="dim-score-denom">{scoreDenom}</span>}
          {delta !== null && <TrendBadge delta={delta} trend={dimension.trend} />}
        </div>
      )}

      <div className="mini-kpi-grid">
        <div className="mini-kpi">
          <p>Total Violations</p>
          <strong>{dimension.totals?.violationCount ?? 0}</strong>
        </div>
        <div className="mini-kpi">
          <p>Total Compliance</p>
          <strong>{dimension.totals?.complianceCount ?? 0}</strong>
        </div>
        <div className="mini-kpi">
          <p>Critical</p>
          <strong>{dimension.totals?.severity?.critical ?? 0}</strong>
        </div>
        <div className="mini-kpi">
          <p>Major</p>
          <strong>{dimension.totals?.severity?.major ?? 0}</strong>
        </div>
      </div>

      {(dimension.violations?.length > 0 || dimension.principles?.length > 0) && (
        <div className="dim-filter-section">
          <div className="filter-row">
            <div className="checkbox-pills">
              {SEVERITY_OPTIONS.map((sev) => (
                <button
                  key={sev}
                  type="button"
                  className={`pill-btn severity-pill ${sev} ${selectedSeverities.includes(sev) ? 'active' : ''}`}
                  aria-pressed={selectedSeverities.includes(sev)}
                  onClick={() => setSelectedSeverities((prev) => toggleInList(prev, sev))}
                >
                  {sev}
                </button>
              ))}
            </div>

            {fileFilter.trim() === '' ? (
              <input
                className="file-filter-input"
                type="text"
                placeholder="Filter by file..."
                aria-label="Filter by file"
                value={fileFilter}
                onChange={(e) => setFileFilter(e.target.value)}
              />
            ) : (
              <span className="active-filter-tag">
                File: {fileFilter}
                <button type="button" onClick={() => setFileFilter('')}>&times;</button>
              </span>
            )}

            {activeFilterCount > 0 && (
              <button type="button" className="clear-filters-btn" onClick={clearAllFilters}>
                Clear filters ({activeFilterCount})
              </button>
            )}
          </div>

          {principleOptions.length > 0 && (
            <div className="dim-principles-filter">
              <p className="filter-section-label">Principles</p>
              <div className="checkbox-pills">
                {principleOptions.map((name) => (
                  <button
                    key={name}
                    type="button"
                    className={`pill-btn ${selectedPrinciples.includes(name) ? 'active' : ''}`}
                    onClick={() => setSelectedPrinciples((prev) => toggleInList(prev, name))}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {dimension.principles?.length > 0 && (
        <div className="dim-principles-list">
          <p className="filter-section-label">
            Principles ({dimension.principles.length})
          </p>
          <div className="principle-accordion-list">
            {dimension.principles.map((principle) => (
              <PrincipleAccordion key={principle.name} principle={principle} />
            ))}
          </div>
        </div>
      )}

      {filteredViolations.length > 0 && (
        <div className="dim-violations-section">
          <div className="section-title-row compact">
            <h4>
              Violations
              {activeFilterCount > 0
                ? ` (${filteredViolations.length} of ${dimension.violations?.length ?? 0})`
                : ` (${filteredViolations.length})`}
            </h4>
            <CopyButton
              label="Fix plan"
              onClick={() => navigator.clipboard.writeText(buildFixPlan())}
            />
          </div>

          <div className="violation-list">
            {filteredViolations.map((entry, index) => (
              <div key={index} className="violation-row">
                <span className={`severity-tag ${entry.severity || 'unknown'}`}>
                  {entry.severity || 'unknown'}
                </span>
                <span className="violation-row-principle">{entry.principle || '-'}</span>
                <span className="violation-row-file">
                  {entry.file
                    ? `${entry.file}${entry.line ? `:${entry.line}` : ''}`
                    : '-'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {filteredViolations.length === 0 && activeFilterCount > 0 && (
        <p className="no-data-cell">No violations match current filters.</p>
      )}
    </section>
  );
}
