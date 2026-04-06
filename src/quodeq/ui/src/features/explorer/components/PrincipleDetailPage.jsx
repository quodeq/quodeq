import { memo, useState, useCallback, useMemo } from 'react';
import { buildSingleViolationPlanText } from '../../../utils/planBuilder.js';
import { buildPrinciplePlanText } from '../../../utils/planTextBuilders.js';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER, gradeColorClass } from '../../../utils/formatters.js';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { getRescore } from '../../../api/index.js';
import { EvalViolationCard, ComplianceCard } from './EvalCards.jsx';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';

const PAGE_SIZE = 20;

function ViolationListSection({ violationsBySeverity, principle, buildViolationPlanText, onDismiss }) {
  return EVAL_SEVERITY_ORDER.map((sev) => {
    const vs = violationsBySeverity[sev];
    if (!vs || vs.length === 0) return null;
    return (
      <div key={sev}>
        <div className="violation-group-header">
          <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
          <span className="violation-group-count">{vs.length}</span>
        </div>
        <div className="vlive-violations-group">
          {vs.map((v, idx) => (
            <EvalViolationCard key={idx} v={v} principle={principle} buildViolationPlanText={buildViolationPlanText} index={idx} onDismiss={onDismiss} />
          ))}
        </div>
      </div>
    );
  });
}

function ComplianceListSection({ data, controls }) {
  const { compliance, displayedCompliance, principle } = data;
  const { hasMore, showAll, setShowAll } = controls;
  if (compliance.length === 0) return null;
  return (
    <div>
      <div className="violation-group-header">
        <span className="violation-group-title">Compliance</span>
        <span className="violation-group-count">{compliance.length}</span>
      </div>
      <div className="vlive-violations-group">
        {displayedCompliance.map((c, idx) => (
          <ComplianceCard key={idx} c={c} principle={principle} index={idx} />
        ))}
      </div>
      {hasMore && (
        <button
          className="offending-show-more"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? 'Show less' : `Show all ${compliance.length} compliance items`}
        </button>
      )}
    </div>
  );
}

function buildViolationPlanText(v, principle) {
  return buildSingleViolationPlanText(v, principle, { reqRefs: v.reqRefs, reqFallback: v.req || undefined });
}

function SeverityTags({ sevCounts }) {
  return (
    <>
      {sevCounts.critical > 0 && <span className="file-detail-stat severity-tag critical">{sevCounts.critical} critical</span>}
      {sevCounts.major > 0 && <span className="file-detail-stat severity-tag major">{sevCounts.major} major</span>}
      {sevCounts.minor > 0 && <span className="file-detail-stat severity-tag minor">{sevCounts.minor} minor</span>}
      {(sevCounts.critical > 0 || sevCounts.major > 0 || sevCounts.minor > 0) && <span className="file-detail-stat-sep">·</span>}
    </>
  );
}

function ComplianceStats({ compliance, violations }) {
  if (compliance.length === 0) return null;
  return (
    <>
      <span className="file-detail-stat-sep">·</span>
      <span className="file-detail-stat"><strong>{compliance.length}</strong> compliance</span>
      {violations.length > 0 && (
        <>
          <span className="file-detail-stat-sep">·</span>
          <span className="file-detail-stat"><strong>1:{Math.round(compliance.length / violations.length)}</strong> ratio</span>
        </>
      )}
    </>
  );
}

function PrincipleHeader({ data, onCopyPlan }) {
  const { principle, score, grade, violations, compliance, sevCounts } = data;
  return (
    <section className="panel file-detail-summary-panel">
      <div className="file-detail-stats-row">
        <div className="file-detail-stats">
          <h3 className="file-detail-title" style={{ margin: 0 }}>{principle}</h3>
          {grade === 'Insufficient' ? (
            <span className="exec-summary-insufficient">Not enough evidence</span>
          ) : (
            <>
              {score && (
                <>
                  <span className="file-detail-stat-sep">·</span>
                  <span className="file-detail-stat" style={{ fontSize: '1.1rem' }}><strong>{score.replace('/10', '')}</strong></span>
                </>
              )}
              <span className="file-detail-stat-sep">·</span>
              <span className={`chip small ${gradeColorClass(grade)}`}>{grade || '—'}</span>
            </>
          )}
        </div>
        {violations.length > 0 && (
          <CopyButton
            label="Full fix plan"
            className="fix-plan-btn-header"
            icon={<SparkleIcon />}
            onClick={onCopyPlan}
          />
        )}
      </div>
      <div className="file-detail-stats" style={{ marginTop: 6 }}>
        <SeverityTags sevCounts={sevCounts} />
        <span className="file-detail-stat"><strong>{violations.length}</strong> violations</span>
        <ComplianceStats compliance={compliance} violations={violations} />
      </div>
    </section>
  );
}

function computeEvalPrincipleData(evalPrincipal) {
  const { principleData, dimViolations = [], dimCompliance = [] } = evalPrincipal;
  const violations = (principleData?.violations?.length > 0) ? principleData.violations : dimViolations;
  const compliance = dimCompliance.filter((c) => c.file || c.reason || c.snippet);
  const violationsBySeverity = EVAL_SEVERITY_ORDER.reduce((acc, sev) => {
    acc[sev] = violations.filter((v) => (v.severity || 'minor').toLowerCase() === sev);
    return acc;
  }, {});
  const sevCounts = { critical: 0, major: 0, minor: 0 };
  violations.forEach(v => { const s = (v.severity || 'minor').toLowerCase(); if (sevCounts[s] !== undefined) sevCounts[s]++; });
  return { violations, compliance, violationsBySeverity, sevCounts };
}

function PrincipleContext({ principleData }) {
  return (
    <>
      {principleData?.findings && (
        <p className="violation-context-desc" style={{ padding: '0 4px', marginBottom: '4px' }}>{principleData.findings}</p>
      )}
      {principleData?.justification && (
        <p className="violation-context-desc muted" style={{ padding: '0 4px', marginBottom: '12px' }}>{principleData.justification}</p>
      )}
    </>
  );
}

const PrincipleDetailPage = memo(function PrincipleDetailPage({ evalPrincipal, severityFilter, onDismiss }) {
  const { principleData, principle, score, grade, dimension, project, runId } = evalPrincipal;
  const [showAllCompliance, setShowAllCompliance] = useState(false);
  const [dismissedSet, setDismissedSet] = useState(new Set());
  const [liveScore, setLiveScore] = useState(null);
  const [liveGrade, setLiveGrade] = useState(null);
  const [activeSevFilter, setActiveSevFilter] = useState(severityFilter || null);
  const { violations, compliance, violationsBySeverity, sevCounts } = computeEvalPrincipleData(evalPrincipal);
  const displayedCompliance = showAllCompliance ? compliance : compliance.slice(0, PAGE_SIZE);

  const handleDismiss = useCallback((v) => {
    if (!onDismiss) return;
    onDismiss(v);
    setDismissedSet((prev) => new Set(prev).add(`${v.file}:${v.line}`));
    // Fire rescore to update principle score/grade
    if (project && runId) {
      getRescore(project, runId).then((rescored) => {
        const dimData = (rescored.dimensions || []).find((d) => d.dimension === dimension);
        if (!dimData) return;
        const pg = (dimData.principles || []).find((p) => p.principle === principle);
        if (pg) { setLiveScore(pg.score); setLiveGrade(pg.grade); }
      }).catch(() => {});
    }
  }, [onDismiss, project, runId, dimension, principle]);

  // Filter dismissed violations and recompute derived stats
  const { filteredBySeverity, filteredViolations, liveSevCounts } = useMemo(() => {
    const bySev = {};
    for (const sev of Object.keys(violationsBySeverity)) {
      bySev[sev] = (violationsBySeverity[sev] || []).filter(
        (v) => !dismissedSet.has(`${v.file}:${v.line}`)
      );
    }
    const allFiltered = Object.values(bySev).flat();
    const counts = { critical: 0, major: 0, minor: 0 };
    allFiltered.forEach((v) => { const s = (v.severity || 'minor').toLowerCase(); if (counts[s] !== undefined) counts[s]++; });
    return { filteredBySeverity: bySev, filteredViolations: allFiltered, liveSevCounts: counts };
  }, [violationsBySeverity, dismissedSet]);

  // Apply active severity filter
  const displayedBySeverity = useMemo(() => {
    if (!activeSevFilter || activeSevFilter === 'all') return filteredBySeverity;
    const filtered = {};
    for (const sev of Object.keys(filteredBySeverity)) {
      filtered[sev] = sev === activeSevFilter ? filteredBySeverity[sev] : [];
    }
    return filtered;
  }, [filteredBySeverity, activeSevFilter]);

  return (
    <>
      <PrincipleHeader
        data={{ principle, score: liveScore ?? score, grade: liveGrade ?? grade, violations: filteredViolations, compliance, sevCounts: liveSevCounts }}
        onCopyPlan={() => copyToClipboard(buildPrinciplePlanText(principle, violations, violationsBySeverity, principleData))}
      />
      <PrincipleContext principleData={principleData} />
      {filteredViolations.length > 0 && (
        <SeverityFilterPills counts={liveSevCounts} activeFilter={activeSevFilter} onFilterChange={setActiveSevFilter} />
      )}
      <ViolationListSection violationsBySeverity={displayedBySeverity} principle={principle} buildViolationPlanText={(v) => buildViolationPlanText(v, principle)} onDismiss={handleDismiss} />
      <ComplianceListSection
        data={{ compliance, displayedCompliance, principle }}
        controls={{ hasMore: compliance.length > PAGE_SIZE, showAll: showAllCompliance, setShowAll: setShowAllCompliance }}
      />
    </>
  );
});

export default PrincipleDetailPage;
