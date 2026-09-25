import { memo, useMemo, useEffect } from 'react';
import { gradeLetter } from '../../../utils/formatters.js';
import { KNOWN_SEVERITIES } from '../../../utils/constants.js';
import { EvalViolationCard, ComplianceCard } from './EvalCards.jsx';
import { ROW_KIND } from './findingListRows.js';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';
import { useStandardDescriptions } from '../hooks/useStandardDescriptions.js';
import { usePrincipleFiltering } from './principleFiltering.js';
import { usePrincipleReportSpec } from './usePrincipleReportSpec.jsx';
import { usePrincipleFixPlanSpec } from './usePrincipleFixPlanSpec.jsx';
import { useDashboardScrollElement } from './VirtualList.jsx';
import DeferredViolationList from './DeferredViolationList.jsx';
import { t } from '../../../strings/index.js';
import { GRADE } from '../../../vocab/grade.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { SEVERITY_FILTER_ALL } from '../../../vocab/severity.js';

// Rows are virtualized (same VirtualList as FileDetailPage): a principle can
// carry hundreds of findings, and each card runs pretext measurement layout
// effects on mount — rendering them all before first paint froze the page for
// seconds with no spinner. React now holds ~30 row instances at once.

// The compliance section shows unless the user has narrowed to one severity:
// no filter, the explicit "all", and the compliance-only view all keep it.
function showsComplianceSection(activeSevFilter) {
  return !activeSevFilter || activeSevFilter === SEVERITY_FILTER_ALL || activeSevFilter === FINDING_TYPE.COMPLIANCE;
}

function buildListItems({ displayedBySeverity, compliance, activeSevFilter }) {
  const arr = [];
  if (activeSevFilter !== FINDING_TYPE.COMPLIANCE) {
    for (const sev of KNOWN_SEVERITIES) {
      const vs = displayedBySeverity[sev];
      if (!vs || vs.length === 0) continue;
      arr.push({ kind: ROW_KIND.SEV_HEADER, sev, count: vs.length });
      vs.forEach((v, idx) => arr.push({ kind: FINDING_TYPE.VIOLATION, v, idx }));
    }
  }
  if (showsComplianceSection(activeSevFilter) && compliance.length > 0) {
    arr.push({ kind: ROW_KIND.COMPLIANCE_HEADER, count: compliance.length });
    compliance.forEach((c, idx) => arr.push({ kind: FINDING_TYPE.COMPLIANCE, c, idx }));
  }
  return arr;
}

// Estimated row heights for the virtualizer: a finding/compliance card
// (also the estimate for a row not materialised yet) vs a section header row.
const ROW_HEIGHT_PX = Object.freeze({ missing: 160, header: 36, row: 160 });

function principleFindingKey(item) {
  if (item.kind === FINDING_TYPE.VIOLATION) return `v-${item.v.file || ''}:${item.v.line ?? ''}:${item.idx}`;
  return `c-${item.c.file || ''}:${item.c.line ?? ''}:${item.idx}`;
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

function PrincipleHeader({ data }) {
  const { principle, description, score, grade, violations, compliance, sevCounts, dateLabel, runId } = data;
  const scoreDisplay = score ? String(score).replace('/10', '') : '—';
  const ratioDisplay = (compliance.length > 0 && violations.length > 0)
    ? `1:${Math.round(compliance.length / violations.length)}`
    : '—';

  const scoreHint = grade === GRADE.INSUFFICIENT
    ? t('explorer.notEnoughEvidence')
    : grade ? t('overview.gradeHint', { letter: gradeLetter(grade) }) : null;

  return (
    <section className="principle-detail-header principle-detail-header--terminal">
      <div className="principle-detail-header__top">
        <TermHeader
          name={(principle || '').toLowerCase()}
          description={description}
          sub={dateLabel || runId || null}
        />
      </div>
      <StatStrip cards>
        <Stat label={t('overview.statScore')} value={scoreDisplay} hint={scoreHint} />
        <Stat label={t('overview.statViolations')} value={violations.length} hint={<SevBadgeRow sevCounts={sevCounts} />} />
        <Stat label={t('overview.statCompliance')} value={compliance.length} />
        <Stat label={t('overview.statRatio')} value={ratioDisplay} hint={t('overview.ratioHint')} />
      </StatStrip>
    </section>
  );
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

function renderPrincipleItem(item, { principle, cardDismiss }) {
  switch (item.kind) {
    case ROW_KIND.SEV_HEADER:
      return <SectionLabel>{item.sev.toUpperCase()} · {item.count}</SectionLabel>;
    case ROW_KIND.COMPLIANCE_HEADER:
      return <SectionLabel>{t('overview.statCompliance')} · {item.count}</SectionLabel>;
    case FINDING_TYPE.VIOLATION:
      return <EvalViolationCard v={item.v} principle={principle} index={item.idx} onDismiss={cardDismiss} />;
    case FINDING_TYPE.COMPLIANCE:
      return <ComplianceCard c={item.c} principle={principle} index={item.idx} />;
    default:
      return null;
  }
}

/** Header, context blurb, severity filter pills, and the deferred
 * virtualized item list. */
function PrincipleDetailBody({
  principle, principleDescription, liveScore, score, liveGrade, grade, filteredViolations, compliance,
  liveSevCounts, dateLabel, runId, principleData, activeSevFilter, setActiveSevFilter, items, virtualKey,
  scrollElement, cardDismiss,
}) {
  return (
    <>
      <PrincipleHeader
        data={{ principle, description: principleDescription, score: liveScore ?? score, grade: liveGrade ?? grade, violations: filteredViolations, compliance, sevCounts: liveSevCounts, dateLabel, runId }}
      />
      <PrincipleContext principleData={principleData} />
      {(filteredViolations.length > 0 || compliance.length > 0) && (
        <SeverityFilterPills
          counts={liveSevCounts}
          complianceCount={compliance.length}
          activeFilter={activeSevFilter}
          onFilterChange={setActiveSevFilter}
        />
      )}
      <DeferredViolationList
        resetKey={virtualKey}
        items={items}
        scrollElement={scrollElement}
        rowHeights={ROW_HEIGHT_PX}
        findingKey={principleFindingKey}
        renderItem={(item) => renderPrincipleItem(item, { principle, cardDismiss })}
      />
    </>
  );
}

export default memo(function PrincipleDetailPage({ evalPrincipal, severityFilter, onDismiss }) {
  const { principleData, principle, score, grade, dimension, runId, dateLabel } = evalPrincipal;
  const { principleDescriptions } = useStandardDescriptions(dimension);
  const principleDescription = principleDescriptions[principle] || '';

  const {
    compliance, liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, filteredViolations, liveSevCounts, displayedBySeverity,
  } = usePrincipleFiltering(evalPrincipal, severityFilter, onDismiss);

  usePrincipleReportSpec({
    principle, dimension, runId, score, grade, liveScore, liveGrade,
    filteredViolations, compliance, principleData, activeSevFilter,
  });
  usePrincipleFixPlanSpec({ principle, dimension, runId, filteredViolations, principleData, activeSevFilter });

  const items = useMemo(
    () => buildListItems({ displayedBySeverity, compliance, activeSevFilter }),
    [displayedBySeverity, compliance, activeSevFilter],
  );

  const scrollElement = useDashboardScrollElement();

  // Snap to top whenever the filter changes so a giant list doesn't dump the
  // user mid-scroll into a freshly-mounted virtualizer.
  useEffect(() => {
    if (scrollElement) scrollElement.scrollTop = 0;
  }, [activeSevFilter, scrollElement]);

  // Remount the virtualizer whenever the items collection changes shape so
  // stale cached row heights can't misplace recycled rows.
  const virtualKey = `${activeSevFilter ?? 'all'}-${filteredViolations.length}-${principle}`;
  // handleDismiss is always a stable no-op-safe function (usePrincipleData's
  // contract), but EvalViolationCard's dismiss button gates on THIS prop
  // being truthy — gate on the original onDismiss so shared projects
  // (App.jsx passes onDismiss={undefined}) don't show a button that no-ops.
  const cardDismiss = onDismiss ? handleDismiss : undefined;

  return (
    <PrincipleDetailBody
      principle={principle} principleDescription={principleDescription} liveScore={liveScore} score={score}
      liveGrade={liveGrade} grade={grade} filteredViolations={filteredViolations} compliance={compliance}
      liveSevCounts={liveSevCounts} dateLabel={dateLabel} runId={runId} principleData={principleData}
      activeSevFilter={activeSevFilter} setActiveSevFilter={setActiveSevFilter} items={items}
      virtualKey={virtualKey} scrollElement={scrollElement} cardDismiss={cardDismiss}
    />
  );
});
