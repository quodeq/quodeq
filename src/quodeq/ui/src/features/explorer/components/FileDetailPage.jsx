import { memo, useCallback, useMemo, useState } from 'react';
import { buildFilePlanText } from '../../../utils/planTextBuilders.js';
import { buildFileReport } from '../../../utils/reportBuilder.js';
import { SEVERITY_ORDER, parseFileRef, complianceRatio } from '../../../utils/formatters.js';
import { SparkleIcon } from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { ComplianceCard } from './EvalCards.jsx';
import { TermHeader, StatStrip, Stat, SevBadge } from '../../../components/terminal/index.js';
import { useRegisterWindowSpec, ReportContent, useSidePane, violationFixPlanSpec } from '../../side-pane/index.js';
import LowConfidenceGroup, { isLowConfidence } from '../../violations/components/LowConfidenceGroup.jsx';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function ViolationCard({ v, index, onDismiss }) {
  const { addWindow } = useSidePane();
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;
  const linkedRefs = v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url)) || [];
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        {v.dimension && <span className="vrow-label">[{v.dimension}]</span>}
        {v.principle && <span className="vrow-label">[{v.principle}]</span>}
        {filename && (
          <FileCopyBtn display={display} copyText={ref} />
        )}
        <button
          type="button"
          className="fix-plan-btn"
          onClick={() => { const spec = violationFixPlanSpec(v); if (spec) addWindow(spec); }}
        >
          <SparkleIcon />
          Fix plan
        </button>
        {onDismiss && (
          <button
            type="button"
            className="dismiss-btn"
            onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
            title="Dismiss this finding (exclude from scoring)"
            aria-label="Dismiss this finding (exclude from scoring)"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        )}
      </div>
      <div className="vlive-detail">
        {(v.title || v.reason) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              <span className="vlive-detail-section-label">Reason</span>
              {linkedRefs.length > 0 &&
                <span className="cwe-link-group">{linkedRefs.map((ref, i) => (
                  <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
                ))}</span>
              }
            </div>
            {v.title && <p className="vlive-detail-title">{v.title}</p>}
            {v.reason && <>
              <span className="vlive-detail-section-label">Detail</span>
              <p className="vlive-detail-reason">{v.reason}</p>
            </>}
          </div>
        )}
        <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} line={v.line} endLine={v.endLine} />
      </div>
    </div>
  );
}

function FileSevBadgeRow({ sevCounts }) {
  if (!(sevCounts.critical || sevCounts.major || sevCounts.minor)) return null;
  return (
    <span className="principle-detail-sev-row">
      {sevCounts.critical > 0 && <SevBadge level="critical" count={sevCounts.critical} format="count-abbr" />}
      {sevCounts.major    > 0 && <SevBadge level="major"    count={sevCounts.major}    format="count-abbr" />}
      {sevCounts.minor    > 0 && <SevBadge level="minor"    count={sevCounts.minor}    format="count-abbr" />}
    </span>
  );
}

function FileHeader({ file, sevCounts, totalViolations, totalCompliance, dimensionsCount, dateLabel, runId }) {
  const totalChecks = totalViolations + totalCompliance;
  const ratio = complianceRatio(totalViolations, totalCompliance);
  return (
    <section className="principle-detail-header principle-detail-header--terminal">
      <div className="principle-detail-header__top">
        <TermHeader name={file.file} sub={dateLabel || runId || null} />
      </div>
      <StatStrip cards>
        <Stat
          label="VIOLATIONS"
          value={totalViolations}
          hint={<FileSevBadgeRow sevCounts={sevCounts} />}
        />
        <Stat
          label="COMPLIANCE"
          value={totalCompliance}
          hint={totalChecks > 0 ? `passing / ${totalChecks} checks` : null}
        />
        <Stat
          label="RATIO"
          value={ratio}
          hint="compliance : violations"
        />
        <Stat
          label="DIMENSIONS"
          value={dimensionsCount}
        />
      </StatStrip>
    </section>
  );
}


function SeverityGroup({ sev, violations, onDismiss }) {
  if (violations.length === 0) return null;
  return (
    <div>
      <div className="violation-group-header">
        <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
        <span className="violation-group-count">{violations.length}</span>
      </div>
      <div className="vlive-violations-group">
        {violations.map((v, idx) => (
          <ViolationCard key={idx} v={v} index={idx} onDismiss={onDismiss} />
        ))}
      </div>
    </div>
  );
}

const FileDetailPage = memo(function FileDetailPage({ file, runId, dateLabel, onDismiss }) {
  const totalCompliance = file.compliance?.length || 0;
  const dimensionsCount = file.dimensionsCount || 0;
  const [activeFilter, setActiveFilter] = useState(null);
  const [dismissedSet, setDismissedSet] = useState(new Set());

  const dismissKey = (v) => `${v.file}:${v.line}`;

  const handleDismiss = useCallback((v) => {
    if (!onDismiss) return;
    onDismiss(v);
    setDismissedSet((prev) => new Set(prev).add(dismissKey(v)));
  }, [onDismiss]);

  const { lowConfidenceViolations, highConfidenceBySeverity, liveSevCounts, liveTotal } = useMemo(() => {
    const low = [];
    const high = {};
    const counts = { critical: 0, major: 0, minor: 0 };
    let total = 0;
    for (const sev of SEVERITY_ORDER) {
      const bucket = (file.violationsBySeverity?.[sev] || []).filter((v) => !dismissedSet.has(dismissKey(v)));
      const highBucket = [];
      for (const v of bucket) {
        if (isLowConfidence(v)) low.push(v);
        else highBucket.push(v);
      }
      high[sev] = highBucket;
      if (counts[sev] !== undefined) counts[sev] = bucket.length;
      total += bucket.length;
    }
    return { lowConfidenceViolations: low, highConfidenceBySeverity: high, liveSevCounts: counts, liveTotal: total };
  }, [file.violationsBySeverity, dismissedSet]);

  const totalViolations = liveTotal;
  const distinctSeverities = SEVERITY_ORDER.filter((s) => liveSevCounts[s] > 0).length;
  const showFilters = distinctSeverities > 1 || (distinctSeverities >= 1 && totalCompliance > 0);
  const showCompliance = !activeFilter || activeFilter === 'all' || activeFilter === 'compliance';
  const showViolations = activeFilter !== 'compliance';

  const reportSpec = useMemo(() => {
    if (!file?.file) return null;
    const buildMarkdown = () => buildFileReport(file);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `report:file:${file.file}`,
      type: 'report',
      title: `${file.file.split('/').pop()} report`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-report.md`, body: buildMarkdown() }),
    };
  }, [file]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!file?.file || (file.total || 0) === 0) return null;
    const buildMarkdown = () => buildFilePlanText(file);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `fixplan:file:${file.file}`,
      type: 'fixplan',
      title: `${file.file.split('/').pop()} fix plan`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [file]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

  return (
    <>
      <FileHeader
        file={file}
        sevCounts={liveSevCounts}
        totalViolations={totalViolations}
        totalCompliance={totalCompliance}
        dimensionsCount={dimensionsCount}
        dateLabel={dateLabel}
        runId={runId}
      />

      {showFilters && (
        <SeverityFilterPills
          counts={liveSevCounts}
          complianceCount={totalCompliance}
          activeFilter={activeFilter}
          onFilterChange={setActiveFilter}
        />
      )}

      {showViolations && SEVERITY_ORDER.map((sev) => {
        if (activeFilter && activeFilter !== 'all' && activeFilter !== sev) return null;
        return <SeverityGroup key={sev} sev={sev} violations={highConfidenceBySeverity[sev] || []} onDismiss={onDismiss ? handleDismiss : undefined} />;
      })}

      {showViolations && (!activeFilter || activeFilter === 'all') && (
        <LowConfidenceGroup
          violations={lowConfidenceViolations}
          renderViolation={(v, idx) => <ViolationCard key={`lc-${idx}`} v={v} index={idx} onDismiss={onDismiss ? handleDismiss : undefined} />}
        />
      )}

      {showCompliance && totalCompliance > 0 && (
        <div>
          <div className="violation-group-header">
            <span className="violation-group-title">Compliance</span>
            <span className="violation-group-count">{totalCompliance}</span>
          </div>
          <div className="vlive-violations-group">
            {file.compliance.map((c, idx) => (
              <ComplianceCard key={idx} c={c} principle={c.principle} index={idx} />
            ))}
          </div>
        </div>
      )}
    </>
  );
});

export default FileDetailPage;
