/**
 * CompareDimensionView: one dimension across every project in scope, the
 * fleet overview one level down, top to bottom:
 *
 *   summary strip       score, below good, coverage, exposure per size, spread
 *   projects | radar    ranked on the dimension, beside the principles radar
 *   principle matrix    every project against every principle (heatmap)
 *   needs attention     outlier principles and hard drops, when there are any
 *   principle health    grade mix, below good, coverage, leader, trailer
 *
 * One project is ACTIVE at a time: the hovered row in the table or the
 * matrix, else the app's selected project, else the leader. The radar draws
 * it over the dashed principle averages.
 */
import { useMemo, useState } from 'react';
import { t } from '../../../strings/index.js';
import { buildDimensionAttention } from '../compareModel.js';
import { ATTENTION_KIND } from '../compareDimensionView.js';
import CompareDimensionHeader, { DIMENSION_PANEL_ID, dimensionTabId } from './CompareDimensionHeader.jsx';
import CompareAttentionStrip from './CompareAttentionStrip.jsx';
import CompareRadarPanel from './CompareRadarPanel.jsx';
import CompareDimensionKpis from './CompareDimensionKpis.jsx';
import CompareFleetTable from './CompareFleetTable.jsx';
import CompareFleetMatrix from './CompareFleetMatrix.jsx';
import ComparePrincipleHealth from './ComparePrincipleHealth.jsx';
import { dimensionRows } from '../compareDimensionOverview.js';
import { score1 } from '../compareFormatters.js';


function buildAttentionItems(dimAttention, onOpenProject, onOpenPrinciple) {
  return dimAttention.map((item) => ({
    key: `${item.kind}-${item.name}-${item.principleLabel || ''}`,
    level: item.level,
    accentScore: item.kind === ATTENTION_KIND.OUTLIER ? item.score : item.row.score,
    name: item.name,
    onNameClick: () => (item.kind === ATTENTION_KIND.OUTLIER
      ? onOpenPrinciple?.(item.cell)
      : onOpenProject(item.row.id)),
    why: item.kind === ATTENTION_KIND.OUTLIER
      ? [
        t('compare.dimReasonOutlier', { principle: item.principleLabel, score: score1(item.score) }),
        item.gap != null ? t('compare.dimReasonGap', { gap: score1(item.gap) }) : null,
      ].filter(Boolean).join(' · ')
      : t('compare.dimReasonDrop', { delta: score1(item.delta) }),
  }));
}

/** `new Map(pairs)` keeps the LAST pair per key. The lookups below replaced
 * find() calls, which returned the first match, so two principles that
 * collapse to one nameKey ('Error Handling' / 'error handling') must still
 * resolve to the first one. */
function firstWinsMap(pairs) {
  const m = new Map();
  for (const [k, v] of pairs) if (!m.has(k)) m.set(k, v);
  return m;
}

/** The standing every panel highlights: the hovered row while one is
 * hovered, else the app's selected project, else the leader when that
 * selection sits outside this scope (so the radar always has a shape). */
export function resolveActiveStanding(view, focusId, selectedProject) {
  const byId = (id) => (id ? view.standings.find((s) => s.row.id === id) : null);
  return byId(focusId) || byId(selectedProject) || view.lead || null;
}

/** Radar series: the dashed scope average, plus the active standing. */
export function buildRadarSeries(view, active) {
  // One key -> score map, so the axis walk is an O(1) pick per principle
  // instead of a find() over the standing's principles.
  const byKey = (source) => {
    const scores = firstWinsMap(source.principles.map((x) => [x.key, x.score]));
    return view.principles.map((p) => (scores.has(p.key) ? scores.get(p.key) : null));
  };
  return [
    { values: view.principles.map((p) => p.avg), variant: 'average' },
    ...(active ? [{ values: byKey(active), variant: 'project' }] : []),
  ];
}

/**
 * In a dimension context a project opens ITS view of the same dimension
 * (the cross-project explorer entry), not its overview; it falls back to
 * the overview when the run is unknowable, and for remote rows, whose
 * detail pages live behind the shared source.
 */
function projectDimensionOpener(view, onOpenProjectDimension, onOpenProject) {
  return (id) => {
    const s = view.standings.find((x) => x.row.id === id);
    if (s && s.runId && onOpenProjectDimension && !s.row.remote) {
      onOpenProjectDimension({ id, name: s.row.name, source: s.row.source, runId: s.runId, dimName: s.dimName, dateLabel: s.dateLabel });
    } else {
      onOpenProject(id);
    }
  };
}

export default function CompareDimensionView({
  view, board, selectedProject = null, onOpenDimension, onOpenProject, onOpenPrinciple,
  onOpenProjectDimension, scopeCount = null,
}) {
  // One hover for the page: the projects table and the heatmap set it, the
  // radar plots it (null falls back to the selected project, then the leader).
  const [focusId, setFocusId] = useState(null);
  const active = resolveActiveStanding(view, focusId, selectedProject);
  const rows = useMemo(() => dimensionRows(view), [view]);
  const principleBoard = useMemo(() => view.principles.map((p) => ({ key: p.key, label: p.label, avg: p.avg })), [view]);
  const dimAttention = buildDimensionAttention(view);
  const dim = view.label;
  const openProjectDimension = projectDimensionOpener(view, onOpenProjectDimension, onOpenProject);

  return (
    <>
      <CompareDimensionHeader view={view} board={board} onOpenDimension={onOpenDimension} />
      {/* The header's tabs swap this one region, so it is the tab panel they
          control. The class repeats .compare-page's column rhythm. */}
      <div id={DIMENSION_PANEL_ID} role="tabpanel" aria-labelledby={dimensionTabId(view.key)} className="compare-dimension-panel">
        <CompareDimensionKpis view={view} rows={rows} scopeCount={scopeCount ?? rows.length} />
        <div className="compare-dim__pair">
          <CompareFleetTable
            scoredRows={rows} fleetScore={view.avg} hover={focusId} setHover={setFocusId} onOpenProject={openProjectDimension}
            ariaLabel={t('compare.dimTableAria', { dim })}
            header={t('compare.fleetTableHeader', { count: rows.length })}
            note={t('compare.dimTableNote', { dim })}
            showLastScan={false}
          />
          <CompareRadarPanel
            view={view}
            axes={view.principles.map((p) => ({ label: p.label, value: p.avg }))}
            series={buildRadarSeries(view, active)}
            active={active}
          />
        </div>
        <CompareFleetMatrix
          rows={rows} board={principleBoard} fleetScore={view.avg} onOpenProject={onOpenProject}
          ariaLabel={t('compare.principleMatrixAria', { dim })}
          header={t('compare.principleMatrixHeader', { rows: rows.length, cols: principleBoard.length })}
          note={t('compare.principleMatrixNote')}
          onOpenCell={(row, cellDim) => cellDim.cell && onOpenPrinciple?.(cellDim.cell)}
          onHoverRow={setFocusId}
        />
        {/* Dimension-scoped triage: principles where one project sits far
            under the rest, and hard 30-day drops. Renders only when it has
            something to say. */}
        <CompareAttentionStrip
          ariaLabel={t('compare.dimAttentionAria', { dim })}
          noteText={t('compare.dimAttentionNote')}
          items={buildAttentionItems(dimAttention, onOpenProject, onOpenPrinciple)}
        />
        <ComparePrincipleHealth view={view} onOpenPrinciple={onOpenPrinciple} />
      </div>
    </>
  );
}
