import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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
import { isLowConfidence } from '../../violations/components/LowConfidenceGroup.jsx';

function filterTitleSuffix(filter) {
  if (!filter || filter === 'all') return '';
  return ` (${filter})`;
}

const ViolationCard = memo(function ViolationCard({ v, onDismiss }) {
  const { addWindow } = useSidePane();
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;
  const linkedRefs = v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url)) || [];
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`}>
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
});

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

function GroupHeader({ title, count }) {
  return (
    <div className="violation-group-header">
      <span className="violation-group-title">{title}</span>
      <span className="violation-group-count">{count}</span>
    </div>
  );
}

function LowConfidenceToggle({ count, expanded, onToggle }) {
  return (
    <button
      type="button"
      className="violation-group-header low-confidence-group-header"
      aria-expanded={expanded}
      onClick={onToggle}
    >
      <span className="violation-group-title">Low confidence</span>
      <span className="violation-group-count">{count}</span>
      <span className="low-confidence-group-hint">
        {expanded ? 'Hide' : 'Show'} likely false positives
      </span>
    </button>
  );
}

// Virtualizer extracted into its own component so the parent can remount it
// (via `key={activeFilter}`) when the filter changes. A fresh virtualizer
// starts with empty measurement caches, sidestepping the class of bugs
// where stale heights at recycled indices cause row overlap.
function VirtualList({ items, scrollElement, renderItem }) {
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollElement,
    estimateSize: (i) => {
      const item = items[i];
      if (!item) return 140;
      if (item.kind === 'sev-header' || item.kind === 'compliance-header') return 36;
      if (item.kind === 'low-conf-toggle') return 36;
      return 160;
    },
    overscan: 6,
    getItemKey: (i) => {
      const item = items[i];
      if (!item) return i;
      if (item.kind === 'sev-header') return `h-${item.sev}`;
      if (item.kind === 'compliance-header') return 'h-compliance';
      if (item.kind === 'low-conf-toggle') return 'h-lowconf';
      if (item.kind === 'violation') {
        return `v-${item.v.dimension || ''}:${item.v.file || ''}:${item.v.line ?? ''}:${item.v.principle || ''}:${item.v.title || ''}`;
      }
      if (item.kind === 'low-conf-row') {
        return `lc-${item.v.dimension || ''}:${item.v.file || ''}:${item.v.line ?? ''}:${item.v.principle || ''}:${item.v.title || ''}`;
      }
      if (item.kind === 'compliance') {
        return `c-${item.c.dimension || ''}:${item.c.file || ''}:${item.c.line ?? ''}:${item.c.principle || ''}`;
      }
      return i;
    },
  });

  const totalSize = virtualizer.getTotalSize();
  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div className="vlive-violations-virtual" style={{ position: 'relative', width: '100%', height: totalSize }}>
      {virtualItems.map((virtualRow) => {
        const item = items[virtualRow.index];
        if (!item) return null;
        return (
          <div
            key={virtualRow.key}
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${virtualRow.start}px)`,
            }}
          >
            {renderItem(item)}
          </div>
        );
      })}
    </div>
  );
}

const FileDetailPage = memo(function FileDetailPage({ file, runId, dateLabel, onDismiss, severityFilter }) {
  const totalCompliance = file.compliance?.length || 0;
  const dimensionsCount = file.dimensionsCount || 0;
  const [activeFilter, setActiveFilter] = useState(severityFilter || null);
  const [dismissedSet, setDismissedSet] = useState(new Set());
  const [lowConfExpanded, setLowConfExpanded] = useState(false);

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

  // Flatten everything into a single virtualizable items array. Mixing
  // headers + rows in one list lets us virtualize the whole page with one
  // scroller; React never holds more than ~30 row instances at once even on
  // 3k-violation projects.
  const items = useMemo(() => {
    const arr = [];
    if (showViolations) {
      for (const sev of SEVERITY_ORDER) {
        const bucket = highConfidenceBySeverity[sev] || [];
        if (bucket.length === 0) continue;
        if (activeFilter && activeFilter !== 'all' && activeFilter !== sev) continue;
        arr.push({ kind: 'sev-header', sev, count: bucket.length });
        for (const v of bucket) arr.push({ kind: 'violation', v });
      }
      if ((!activeFilter || activeFilter === 'all') && lowConfidenceViolations.length > 0) {
        arr.push({ kind: 'low-conf-toggle', count: lowConfidenceViolations.length, expanded: lowConfExpanded });
        if (lowConfExpanded) {
          for (const v of lowConfidenceViolations) arr.push({ kind: 'low-conf-row', v });
        }
      }
    }
    if (showCompliance && totalCompliance > 0) {
      arr.push({ kind: 'compliance-header', count: totalCompliance });
      for (const c of file.compliance) arr.push({ kind: 'compliance', c });
    }
    return arr;
  }, [showViolations, showCompliance, activeFilter, highConfidenceBySeverity, lowConfidenceViolations, lowConfExpanded, file.compliance, totalCompliance]);

  // The dashboard's main column owns vertical scroll; tanstack-virtual needs
  // a ref to that ancestor to track scroll position.
  const [scrollElement, setScrollElement] = useState(null);
  useLayoutEffect(() => {
    setScrollElement(document.querySelector('.app-shell__main-column > .dashboard'));
  }, []);

  // Snap to top whenever the filter changes so a giant list doesn't dump the
  // user mid-scroll into a freshly-mounted virtualizer.
  useEffect(() => {
    if (scrollElement) scrollElement.scrollTop = 0;
  }, [activeFilter, scrollElement]);

  const reportSpec = useMemo(() => {
    if (!file?.file) return null;
    const buildMarkdown = () => buildFileReport(file, activeFilter);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const baseTitle = `${file.file.split('/').pop()} report`;
    return {
      id: `report:file:${file.file}`,
      type: 'report',
      title: `${baseTitle}${filterTitleSuffix(activeFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-report.md`, body: buildMarkdown() }),
    };
  }, [file, activeFilter]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!file?.file || (file.total || 0) === 0) return null;
    const buildMarkdown = () => buildFilePlanText(file, activeFilter);
    const filenameLabel = file.file.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const baseTitle = `${file.file.split('/').pop()} fix plan`;
    return {
      id: `fixplan:file:${file.file}`,
      type: 'fixplan',
      title: `${baseTitle}${filterTitleSuffix(activeFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `file-${filenameLabel}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [file, activeFilter]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);

  const renderItem = (item) => {
    switch (item.kind) {
      case 'sev-header':
        return <GroupHeader title={item.sev.charAt(0).toUpperCase() + item.sev.slice(1)} count={item.count} />;
      case 'compliance-header':
        return <GroupHeader title="Compliance" count={item.count} />;
      case 'low-conf-toggle':
        return <LowConfidenceToggle count={item.count} expanded={item.expanded} onToggle={() => setLowConfExpanded((v) => !v)} />;
      case 'violation':
      case 'low-conf-row':
        return <ViolationCard v={item.v} onDismiss={onDismiss ? handleDismiss : undefined} />;
      case 'compliance':
        return <ComplianceCard c={item.c} principle={item.c.principle} index={0} />;
      default:
        return null;
    }
  };

  // Remount the virtualizer whenever the items collection changes shape.
  // A fresh useVirtualizer call begins with no cached heights, so the row
  // wrappers re-measure from scratch — eliminating overlap caused by stale
  // measurements lingering from a previous filter or dismiss state.
  const virtualKey = `${activeFilter ?? 'all'}-${dismissedSet.size}-${lowConfExpanded ? 'lc' : ''}-${file?.file || ''}`;

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

      <VirtualList key={virtualKey} items={items} scrollElement={scrollElement} renderItem={renderItem} />
    </>
  );
});

export default FileDetailPage;
