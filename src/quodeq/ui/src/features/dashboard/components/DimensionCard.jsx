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
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { splitScore, gradeColorClass, gradeLetter } from '../../../utils/formatters.js';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { SEVERITY_OPTIONS, toggleInList, computePrincipleOptions, filterViolations } from './dimensionCardModel.js';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';

function PrincipleFilter({ principles }) {
  const { options: principleOptions, selected: selectedPrinciples, setSelected: setSelectedPrinciples } = principles;
  if (principleOptions.length === 0) return null;
  return (
    <div className="dim-principles-filter">
      <p className="filter-section-label">{t('dimension.principlesLabel')}</p>
      <div className="checkbox-pills">
        {principleOptions.map((name) => (
          <button
            key={name}
            type="button"
            className={`pill-btn ${selectedPrinciples.includes(name) ? 'active' : ''}`}
            aria-pressed={selectedPrinciples.includes(name)}
            onClick={() => setSelectedPrinciples((prev) => toggleInList(prev, name))}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}

function DimFilterControls({ severity, file, principles, activeFilterCount, clearAllFilters }) {
  const { selected: selectedSeverities, setSelected: setSelectedSeverities } = severity;
  const { filter: fileFilter, setFilter: setFileFilter } = file;
  return (
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
              {severityLabel(sev)}
            </button>
          ))}
        </div>

        {fileFilter.trim() === '' ? (
          <input
            className="file-filter-input"
            type="text"
            placeholder={t('dimension.filterByFilePlaceholder')}
            aria-label={t('dimension.filterByFileAria')}
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
          />
        ) : (
          <span className="active-filter-tag">
            {t('dimension.fileTag', { name: fileFilter })}
            <button type="button" onClick={() => setFileFilter('')} aria-label={t('dimension.clearFileFilterAria')}>&times;</button>
          </span>
        )}

        {activeFilterCount > 0 && (
          <button type="button" className="clear-filters-btn" onClick={clearAllFilters}>
            {t('dimension.clearFilters', { count: activeFilterCount })}
          </button>
        )}
      </div>

      <PrincipleFilter principles={principles} />
    </div>
  );
}

function DimViolationsList({ filteredViolations, activeFilterCount, totalCount, buildFixPlan }) {
  return (
    <div className="dim-violations-section">
      <div className="section-title-row compact">
        <h4>
          {activeFilterCount > 0
            ? t('dimension.violationsHeadingFiltered', { shown: filteredViolations.length, total: totalCount })
            : t('dimension.violationsHeading', { count: filteredViolations.length })}
        </h4>
        <CopyButton
          label={t('dimension.fullFixPlan')}
          className="fix-plan-btn-header"
          icon={<SparkleIcon />}
          onClick={() => copyToClipboard(buildFixPlan())}
        />
      </div>

      <div className="violation-list">
        {filteredViolations.map((entry, index) => (
          <div key={index} className="violation-row">
            <span className={`severity-tag ${entry.severity || 'unknown'}`}>
              {severityLabel(entry.severity)}
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
  );
}

function DimCardHeader({ title, dimension, delta }) {
  const { value: scoreValue, denom: scoreDenom } = splitScore(dimension.overallScore);
  return (
    <>
      <div className="compare-column-header">
        <div>
          {title && <p className="brand-overline">{title}</p>}
          <h3>{dimension.dimension}</h3>
        </div>
        <span className={`chip ${gradeColorClass(dimension.overallGrade)}`}>
          {gradeLetter(dimension.overallGrade)}
        </span>
      </div>
      {dimension.overallScore && (
        <div className="dim-score-row">
          <span className="dim-score-value">{scoreValue}</span>
          {scoreDenom && <span className="dim-score-denom">{scoreDenom}</span>}
          {delta !== null && <TrendBadge delta={delta} trend={dimension.trend} />}
        </div>
      )}
    </>
  );
}

function DimKpiGrid({ dimension }) {
  return (
    <div className="mini-kpi-grid">
      <div className="mini-kpi"><p>{t('dimension.kpiTotalViolations')}</p><strong>{dimension.totals?.violationCount ?? 0}</strong></div>
      <div className="mini-kpi"><p>{t('dimension.kpiTotalCompliance')}</p><strong>{dimension.totals?.complianceCount ?? 0}</strong></div>
      <div className="mini-kpi"><p>{t('dimension.kpiCritical')}</p><strong>{dimension.totals?.severity?.critical ?? 0}</strong></div>
      <div className="mini-kpi"><p>{t('dimension.kpiMajor')}</p><strong>{dimension.totals?.severity?.major ?? 0}</strong></div>
    </div>
  );
}

function DimPrinciplesList({ dimension }) {
  if (!dimension.principles?.length) return null;
  return (
    <div className="dim-principles-list">
      <p className="filter-section-label">{t('dimension.principlesCount', { count: dimension.principles.length })}</p>
      <div className="principle-accordion-list">
        {dimension.principles.map((principle) => (
          <PrincipleAccordion key={principle.name} principle={principle} />
        ))}
      </div>
    </div>
  );
}

export default function DimensionCard({ title, dimension, isSingleFocus }) {
  const [selectedSeverities, setSelectedSeverities] = useState([]);
  const [selectedPrinciples, setSelectedPrinciples] = useState([]);
  const [fileFilter, setFileFilter] = useState('');
  const principleOptions = useMemo(() => computePrincipleOptions(dimension), [dimension]);
  const filteredViolations = useMemo(
    () => filterViolations(dimension, selectedSeverities, selectedPrinciples, fileFilter),
    [dimension, selectedSeverities, selectedPrinciples, fileFilter]
  );
  const activeFilterCount = (selectedSeverities.length > 0 ? 1 : 0) + (selectedPrinciples.length > 0 ? 1 : 0) + (fileFilter.trim() ? 1 : 0);
  const clearAllFilters = () => { setSelectedSeverities([]); setSelectedPrinciples([]); setFileFilter(''); };
  const buildFixPlan = () => buildDimensionPlanFromViolations(dimension?.dimension || title || 'dimension', filteredViolations);

  if (!dimension) {
    return <section className="panel dim-card"><h3>{title}</h3><p className="dimension-meta">{t('dimension.selectDimension')}</p></section>;
  }

  const currScore = parseFloat(dimension.overallScore);
  const prevScore = parseFloat(dimension.previousScore);
  const delta = !isNaN(currScore) && !isNaN(prevScore) ? (currScore - prevScore) : null;

  return (
    <section className={`panel dim-card ${isSingleFocus ? 'full-width' : ''}`}>
      <DimCardHeader title={title} dimension={dimension} delta={delta} />
      <DimKpiGrid dimension={dimension} />
      {(dimension.violations?.length > 0 || dimension.principles?.length > 0) && (
        <DimFilterControls
          severity={{ selected: selectedSeverities, setSelected: setSelectedSeverities }}
          file={{ filter: fileFilter, setFilter: setFileFilter }}
          principles={{ options: principleOptions, selected: selectedPrinciples, setSelected: setSelectedPrinciples }}
          activeFilterCount={activeFilterCount}
          clearAllFilters={clearAllFilters}
        />
      )}
      <DimPrinciplesList dimension={dimension} />
      {filteredViolations.length > 0 && (
        <DimViolationsList filteredViolations={filteredViolations} activeFilterCount={activeFilterCount} totalCount={dimension.violations?.length ?? 0} buildFixPlan={buildFixPlan} />
      )}
      {filteredViolations.length === 0 && activeFilterCount > 0 && (
        <p className="no-data-cell">{t('dimension.noViolationsMatch')}</p>
      )}
    </section>
  );
}
