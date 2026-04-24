import { memo, useState, useCallback, useMemo } from 'react';
import { buildSingleViolationPlanText } from '../../../utils/planBuilder.js';
import { buildPrinciplePlanText } from '../../../utils/planTextBuilders.js';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER, gradeColorClass } from '../../../utils/formatters.js';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { EvalViolationCard, ComplianceCard } from './EvalCards.jsx';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';
import VirtualList from '../../../components/VirtualList.jsx';

const PAGE_SIZE = 20;

// Pretext-fed estimate for VirtualList. Counts wrap-able characters so the
// initial scroll geometry is close to the final measured height; a post-mount
// ResizeObserver inside VirtualList corrects any drift as cards render.
const VIRTUAL_OVERHEAD = 140;   // header row + labels + padding + scope bar
const CHARS_PER_LINE = 90;      // rough chars that fit at typical container width
const LINE_HEIGHT = 20;

function estimateFindingHeight(v) {
  const titleLines = v?.title ? Math.max(1, Math.ceil(v.title.length / CHARS_PER_LINE)) : 0;
  const reasonLines = v?.reason ? Math.max(1, Math.ceil(v.reason.length / CHARS_PER_LINE)) : 0;
  return VIRTUAL_OVERHEAD + (titleLines + reasonLines) * LINE_HEIGHT;
}

const VIRTUALIZE_THRESHOLD = 20; // only virtualize groups this long

function ViolationListSection({ violationsBySeverity, principle, buildViolationPlanText, onDismiss }) {
  return EVAL_SEVERITY_ORDER.map((sev) => {
    const vs = violationsBySeverity[sev];
    if (!vs || vs.length === 0) return null;
    const renderCard = (v, idx) => (
      <EvalViolationCard v={v} principle={principle} buildViolationPlanText={buildViolationPlanText} index={idx} onDismiss={onDismiss} />
    );
    return (
      <div key={sev}>
        <SectionLabel>{sev.toUpperCase()} · {vs.length}</SectionLabel>
        {vs.length >= VIRTUALIZE_THRESHOLD ? (
          <VirtualList
            className="vlive-violations-group vlive-violations-group--virtual"
            items={vs}
            getEstimatedHeight={estimateFindingHeight}
            getItemKey={(v, i) => `${v.file || 'nofile'}:${v.line ?? 'noline'}:${i}`}
            renderItem={renderCard}
          />
        ) : (
          <div className="vlive-violations-group">
            {vs.map((v, idx) => (
              <EvalViolationCard key={idx} v={v} principle={principle} buildViolationPlanText={buildViolationPlanText} index={idx} onDismiss={onDismiss} />
            ))}
          </div>
        )}
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
      <SectionLabel>COMPLIANCE · {compliance.length}</SectionLabel>
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

function SevBadgeRow({ sevCounts }) {
  if (!(sevCounts.critical || sevCounts.major || sevCounts.minor)) return null;
  return (
    <span className="principle-detail-sev-row">
      {sevCounts.critical > 0 && <SevBadge level="critical" count={sevCounts.critical} />}
      {sevCounts.major > 0    && <SevBadge level="major" count={sevCounts.major} />}
      {sevCounts.minor > 0    && <SevBadge level="minor" count={sevCounts.minor} />}
    </span>
  );
}

function PrincipleHeader({ data, onCopyPlan }) {
  const { principle, score, grade, violations, compliance, sevCounts } = data;
  const scoreDisplay = score ? String(score).replace('/10', '') : '—';
  const ratioDisplay = (compliance.length > 0 && violations.length > 0)
    ? `1:${Math.round(compliance.length / violations.length)}`
    : '—';

  return (
    <section className="principle-detail-header principle-detail-header--terminal">
      <div className="principle-detail-header__top">
        <TermHeader
          name={`${principle}.detail`}
          sub={
            grade === 'Insufficient'
              ? 'not enough evidence'
              : <span className={`chip small ${gradeColorClass(grade)}`}>{grade || '—'}</span>
          }
        />
        {violations.length > 0 && (
          <CopyButton
            label="Full fix plan"
            className="fix-plan-btn-header"
            icon={<SparkleIcon />}
            onClick={onCopyPlan}
          />
        )}
      </div>
      <StatStrip bordered>
        <Stat label="SCORE" value={scoreDisplay} />
        <Stat label="VIOLATIONS" value={violations.length} hint={<SevBadgeRow sevCounts={sevCounts} />} />
        <Stat label="COMPLIANCE" value={compliance.length} />
        <Stat label="RATIO" value={ratioDisplay} hint="compliance : violations" />
      </StatStrip>
    </section>
  );
}

function computeEvalPrincipleData(evalPrincipal) {
  const { principleData, dimViolations = [], dimCompliance = [] } = evalPrincipal;
  const violations = (principleData?.violations?.length > 0) ? principleData.violations : dimViolations;
  const compliance = dimCompliance.filter((c) => c.file || c.reason || c.snippet);
  const violationsBySeverity = {};
  const sevCounts = { critical: 0, major: 0, minor: 0 };
  for (const sev of EVAL_SEVERITY_ORDER) violationsBySeverity[sev] = [];
  for (const v of violations) {
    const sev = (v.severity || 'minor').toLowerCase();
    if (violationsBySeverity[sev]) violationsBySeverity[sev].push(v);
    if (sevCounts[sev] !== undefined) sevCounts[sev]++;
  }
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

function filterBySeveritySelection(filteredBySeverity, activeSevFilter) {
  if (!activeSevFilter || activeSevFilter === 'all') return filteredBySeverity;
  const filtered = {};
  for (const sev of Object.keys(filteredBySeverity)) {
    filtered[sev] = sev === activeSevFilter ? filteredBySeverity[sev] : [];
  }
  return filtered;
}

function usePrincipleFiltering(evalPrincipal, severityFilter, onDismiss) {
  const { getRunScores } = useApi();
  const { principle, dimension, project, runId } = evalPrincipal;
  const [dismissedSet, setDismissedSet] = useState(new Set());
  const [liveScore, setLiveScore] = useState(null);
  const [liveGrade, setLiveGrade] = useState(null);
  const [activeSevFilter, setActiveSevFilter] = useState(severityFilter || null);
  const { violations, compliance, violationsBySeverity } = useMemo(() => computeEvalPrincipleData(evalPrincipal), [evalPrincipal]);

  const handleDismiss = useCallback((v) => {
    if (!onDismiss) return;
    onDismiss(v);
    setDismissedSet((prev) => new Set(prev).add(`${v.file}:${v.line}`));
    if (project && runId) {
      getRunScores(project, runId).then((rescored) => {
        const dimMap = new Map((rescored.dimensions || []).map((d) => [d.dimension, d]));
        const dimData = dimMap.get(dimension);
        if (!dimData) return;
        const pgMap = new Map((dimData.principles || []).map((p) => [p.principle, p]));
        const pg = pgMap.get(principle);
        if (pg) { setLiveScore(pg.score); setLiveGrade(pg.grade); }
      }).catch(() => {});
    }
  }, [onDismiss, project, runId, dimension, principle]);

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

  const displayedBySeverity = useMemo(
    () => filterBySeveritySelection(filteredBySeverity, activeSevFilter),
    [filteredBySeverity, activeSevFilter]
  );

  return {
    violations, compliance, violationsBySeverity,
    liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, filteredViolations, liveSevCounts, displayedBySeverity,
  };
}

const PrincipleDetailPage = memo(function PrincipleDetailPage({ evalPrincipal, severityFilter, onDismiss }) {
  const { principleData, principle, score, grade } = evalPrincipal;
  const [showAllCompliance, setShowAllCompliance] = useState(false);

  const {
    violations, compliance, violationsBySeverity,
    liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, filteredViolations, liveSevCounts, displayedBySeverity,
  } = usePrincipleFiltering(evalPrincipal, severityFilter, onDismiss);

  const displayedCompliance = showAllCompliance ? compliance : compliance.slice(0, PAGE_SIZE);

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
