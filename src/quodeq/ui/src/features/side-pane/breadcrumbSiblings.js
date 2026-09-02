import { labelFor as navLabelFor } from '../explorer/components/NavBreadcrumb.jsx';
import { deriveEvaluatePreselect } from '../../utils/evaluatePreselect.js';

// App.jsx's breadcrumb jump-bar data: which siblings a given path segment
// can swap to. Two levels have a known sibling set — the root tab (the
// sidebar's main destinations) and the explorer dimension. Levels without
// one return null and stay plain links. Extracted verbatim from App.jsx.
export function buildBreadcrumbSiblingsFor({
  selectedProject, navTab, navSwapAt, activePage, filteredAccumulated,
}) {
  return (entry, index) => {
    if (index === 0) {
      if (!selectedProject) return null;
      return ['overview', 'violations', 'map', 'history', 'evaluate'].map((id) => ({
        key: id,
        label: navLabelFor({ page: id }),
        current: entry.page === id,
        onSelect: () => (id === 'evaluate'
          ? navTab('evaluate', { preselectDims: deriveEvaluatePreselect(activePage) })
          : navTab(id)),
      }));
    }
    if (entry.page === 'explorer') {
      const dims = filteredAccumulated?.dimensions || [];
      if (dims.length < 2) return null;
      return dims.map((dim) => ({
        key: dim.dimension,
        label: (dim.dimension || '').toLowerCase(),
        current: dim.dimension === entry.dimension,
        onSelect: () => navSwapAt(index, {
          page: 'explorer',
          dimension: dim.dimension,
          runId: dim.fromRunId,
          dateLabel: dim.fromDateLabel,
          fromProject: dim.fromProject,
          sourceTab: entry.sourceTab || 'violations',
        }),
      }));
    }
    return null;
  };
}
