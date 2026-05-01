import { memo, useState, useCallback, useMemo } from 'react';
import { buildPrinciplePlanText } from '../../../utils/planTextBuilders.js';
import { buildPrincipleReport } from '../../../utils/reportBuilder.js';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER, gradeColorClass } from '../../../utils/formatters.js';
import { useApi } from '../../../api/ApiContext.jsx';
import { EvalViolationCard, ComplianceCard } from './EvalCards.jsx';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { TermHeader, StatStrip, Stat, SevBadge, SectionLabel } from '../../../components/terminal/index.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';

// Off-screen rows skip layout/paint via CSS `content-visibility: auto` on
// `.vdetail-row` (see styles/explorer.css), so no JS virtualizer or
// "Show all" pagination is needed. Rows render naturally inside the app's
// existing scroll container.

function ViolationListSection({ violationsBySeverity, principle, onDismiss }) {
  return EVAL_SEVERITY_ORDER.map((sev) => {
    const vs = violationsBySeverity[sev];
    if (!vs || vs.length === 0) return null;
    return (
      <div key={sev}>
        <SectionLabel>{sev.toUpperCase()} · {vs.length}</SectionLabel>
        <div className="vlive-violations-group">
          {vs.map((v, idx) => (
            <EvalViolationCard
              key={`${v.file || 'nofile'}:${v.line ?? 'noline'}:${idx}`}
              v={v}
              principle={principle}
              index={idx}
              onDismiss={onDismiss}
            />
          ))}
        </div>
      </div>
    );
  });
}

function ComplianceListSection({ compliance, principle }) {
  if (compliance.length === 0) return null;
  return (
    <div>
      <SectionLabel>COMPLIANCE · {compliance.length}</SectionLabel>
      <div className="vlive-violations-group">
        {compliance.map((c, idx) => (
          <ComplianceCard
            key={`${c.file || 'nofile'}:${c.line ?? 'noline'}:${idx}`}
            c={c}
            principle={principle}
            index={idx}
          />
        ))}
      </div>
    </div>
  );
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
  const { principleData, principle, score, grade, dimension, runId } = evalPrincipal;

  const {
    violations, compliance, violationsBySeverity,
    liveScore, liveGrade, activeSevFilter, setActiveSevFilter,
    handleDismiss, filteredViolations, liveSevCounts, displayedBySeverity,
  } = usePrincipleFiltering(evalPrincipal, severityFilter, onDismiss);

  const reportSpec = useMemo(() => {
    if (!principle) return null;
    const buildMarkdown = () => buildPrincipleReport({
      principle, dimension,
      score: liveScore ?? score, grade: liveGrade ?? grade,
      violations: filteredViolations, violationsBySeverity: displayedBySeverity,
      compliance, principleData, runId,
    });
    const slug = `${(dimension || 'dim')}-${principle}`.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `report:principle:${dimension || 'dim'}:${principle}:${runId || 'current'}`,
      type: 'report',
      title: `${principle} report`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `principle-${slug}-report.md`, body: buildMarkdown() }),
    };
  }, [principle, dimension, runId, score, grade, liveScore, liveGrade, filteredViolations, displayedBySeverity, compliance, principleData]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!principle || filteredViolations.length === 0) return null;
    const buildMarkdown = () => buildPrinciplePlanText(principle, violations, violationsBySeverity, principleData);
    const slug = `${(dimension || 'dim')}-${principle}`.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `fixplan:principle:${dimension || 'dim'}:${principle}:${runId || 'current'}`,
      type: 'fixplan',
      title: `${principle} fix plan`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `principle-${slug}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [principle, dimension, runId, violations, violationsBySeverity, principleData, filteredViolations.length]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

  return (
    <>
      <PrincipleHeader
        data={{ principle, score: liveScore ?? score, grade: liveGrade ?? grade, violations: filteredViolations, compliance, sevCounts: liveSevCounts }}
      />
      <PrincipleContext principleData={principleData} />
      {filteredViolations.length > 0 && (
        <SeverityFilterPills counts={liveSevCounts} activeFilter={activeSevFilter} onFilterChange={setActiveSevFilter} />
      )}
      <ViolationListSection
        violationsBySeverity={displayedBySeverity}
        principle={principle}
        onDismiss={handleDismiss}
      />
      <ComplianceListSection compliance={compliance} principle={principle} />
    </>
  );
});

export default PrincipleDetailPage;
