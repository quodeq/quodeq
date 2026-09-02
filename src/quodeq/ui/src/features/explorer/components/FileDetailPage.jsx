import { memo, useEffect, useState } from 'react';
import SeverityFilterPills from '../../../components/SeverityFilterPills.jsx';
import { ComplianceCard } from './EvalCards.jsx';
import ViolationCard from './ViolationCard.jsx';
import FileDetailHeader from './FileDetailHeader.jsx';
import { GroupHeader, LowConfidenceToggle, estimateItemSize, itemKey } from './fileDetailWidgets.jsx';
import { useFileDetailFiltering } from './useFileDetailFiltering.js';
import { useFileDetailWindowSpecs } from './useFileDetailWindowSpecs.jsx';
import VirtualList, { useDashboardScrollElement } from './VirtualList.jsx';
import DeferredMount from './DeferredMount.jsx';
import CardListSkeleton from './CardListSkeleton.jsx';
import { t } from '../../../strings/index.js';
import { severityLabel } from '../../../strings/labels.js';

function renderFileDetailItem(item, { onDismiss, handleDismiss, setLowConfExpanded }) {
  switch (item.kind) {
    case 'sev-header': {
      const label = severityLabel(item.sev);
      return <GroupHeader title={label.charAt(0).toUpperCase() + label.slice(1)} count={item.count} />;
    }
    case 'compliance-header':
      return <GroupHeader title={t('explorer.complianceHeader')} count={item.count} />;
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
}

/** Header, severity filter pills, and the deferred virtualized item list. */
function FileDetailBody({
  file, runId, dateLabel, onDismiss, dimensionsCount, liveSevCounts, liveTotal, totalCompliance,
  showFilters, activeFilter, setActiveFilter, items, virtualKey, scrollElement, handleDismiss, setLowConfExpanded,
}) {
  return (
    <>
      <FileDetailHeader
        file={file}
        sevCounts={liveSevCounts}
        totalViolations={liveTotal}
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

      {/* Same two-commit split as PrincipleDetailPage: this page is param-fed
          (no fetch), so the first paint would otherwise wait for the visible
          cards' pretext layout effects. */}
      <DeferredMount fallback={<CardListSkeleton />}>
        <VirtualList
          key={virtualKey}
          items={items}
          scrollElement={scrollElement}
          estimateSize={estimateItemSize(items)}
          getItemKey={itemKey(items)}
          renderItem={(item) => renderFileDetailItem(item, { onDismiss, handleDismiss, setLowConfExpanded })}
        />
      </DeferredMount>
    </>
  );
}

const FileDetailPage = memo(function FileDetailPage({ file, runId, dateLabel, onDismiss, severityFilter }) {
  const dimensionsCount = file.dimensionsCount || 0;
  const [activeFilter, setActiveFilter] = useState(severityFilter || null);
  const [lowConfExpanded, setLowConfExpanded] = useState(false);

  const {
    dismissedSet, handleDismiss, liveSevCounts, liveTotal, totalCompliance, showFilters, items,
  } = useFileDetailFiltering({ file, onDismiss, activeFilter, lowConfExpanded });

  useFileDetailWindowSpecs({ file, activeFilter });

  const scrollElement = useDashboardScrollElement();

  // Snap to top whenever the filter changes so a giant list doesn't dump the
  // user mid-scroll into a freshly-mounted virtualizer.
  useEffect(() => {
    if (scrollElement) scrollElement.scrollTop = 0;
  }, [activeFilter, scrollElement]);

  // Remount the virtualizer whenever the items collection changes shape.
  // A fresh useVirtualizer call begins with no cached heights, so the row
  // wrappers re-measure from scratch — eliminating overlap caused by stale
  // measurements lingering from a previous filter or dismiss state.
  const virtualKey = `${activeFilter ?? 'all'}-${dismissedSet.size}-${lowConfExpanded ? 'lc' : ''}-${file?.file || ''}`;

  return (
    <FileDetailBody
      file={file} runId={runId} dateLabel={dateLabel} onDismiss={onDismiss}
      dimensionsCount={dimensionsCount} liveSevCounts={liveSevCounts} liveTotal={liveTotal}
      totalCompliance={totalCompliance} showFilters={showFilters} activeFilter={activeFilter}
      setActiveFilter={setActiveFilter} items={items} virtualKey={virtualKey} scrollElement={scrollElement}
      handleDismiss={handleDismiss} setLowConfExpanded={setLowConfExpanded}
    />
  );
});

export default FileDetailPage;
