/**
 * CompareDimensionView — one dimension across every project in scope:
 * stat cards, ranked standings with per-principle bars, a radar of one
 * project over the scope average, the projects x principles matrix and one
 * card per principle. One project is ACTIVE at a time: the hovered row
 * (standings or matrix), else the app's selected project. The radar plots
 * it, both tables highlight it and the principle cards mark its bar.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { buildDimensionAttention } from '../compareModel.js';
import { ATTENTION_KIND } from '../compareDimensionView.js';
import CompareMatrix from './CompareMatrix.jsx';
import CompareDimensionHeader, { DIMENSION_PANEL_ID, dimensionTabId } from './CompareDimensionHeader.jsx';
import CompareDimensionStatCards from './CompareDimensionStatCards.jsx';
import CompareAttentionStrip from './CompareAttentionStrip.jsx';
import CompareStandingsList from './CompareStandingsList.jsx';
import CompareRadarPanel from './CompareRadarPanel.jsx';
import ComparePrincipleCards from './ComparePrincipleCards.jsx';
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

export function buildDimensionMatrixRows(view, onOpenProject, onOpenPrinciple) {
  // Each principle's cells keyed by project id once, so the standings x
  // principles walk below never rescans perProject.
  const cellsById = view.principles.map((p) => firstWinsMap(p.perProject.map((x) => [x.id, x])));
  return view.standings.map((s) => ({
    id: s.row.id,
    name: s.row.name,
    remote: s.row.remote,
    overall: s.score,
    onOpenRow: () => onOpenProject(s.row.id),
    cells: Object.fromEntries(view.principles.map((p, i) => {
      const cell = cellsById[i].get(s.row.id);
      if (!cell) return [p.key, { score: null }];
      return [p.key, {
        score: cell.score,
        title: t('compare.openDimensionIn', { dim: p.label, project: s.row.name }),
        onClick: onOpenPrinciple ? () => onOpenPrinciple(cell) : undefined,
      }];
    })),
  }));
}

/** v4c appendix: the same matrix grammar as the fleet's SCORE_MATRIX, one
 * level deeper — projects x principles, cells opening that project's own
 * principle page. Hovering a row makes that project the view's active one. */
function PrincipleMatrix({ view, activeId, setFocusId, onOpenProject, onOpenPrinciple }) {
  return (
    <CompareMatrix
      ariaLabel={t('compare.principleMatrixAria', { dim: view.label })}
      header={t('compare.principleMatrixHeader', { rows: view.standings.length, cols: view.principles.length })}
      note={t('compare.matrixNote')}
      footOverall={view.avg}
      columns={view.principles.map((p) => ({ key: p.key, label: p.label, avg: p.avg }))}
      matrixRows={buildDimensionMatrixRows(view, onOpenProject, onOpenPrinciple)}
      activeRowId={activeId}
      onHoverRow={setFocusId}
    />
  );
}

export default function CompareDimensionView({
  view, board, selectedProject = null, onOpenDimension, onOpenProject, onOpenPrinciple,
  onOpenProjectDimension,
}) {
  // Hover state shared by the standings, the matrix and the principle
  // bars; null falls back to the selected project (resolveActiveStanding).
  const [focusId, setFocusId] = useState(null);
  const active = resolveActiveStanding(view, focusId, selectedProject);
  const activeId = active?.row.id ?? null;
  const dimAttention = buildDimensionAttention(view);
  const axes = view.principles.map((p) => ({ label: p.label, value: p.avg }));
  const series = buildRadarSeries(view, active);

  return (
    <>
      <CompareDimensionHeader view={view} board={board} onOpenDimension={onOpenDimension} />
      {/* The header's tabs swap this one region, so it is the tab panel they
          control. The class repeats .compare-page's column rhythm, which the
          sections used to get as direct children of the page. */}
      <div
        id={DIMENSION_PANEL_ID}
        role="tabpanel"
        aria-labelledby={dimensionTabId(view.key)}
        className="compare-dimension-panel"
      >
        <CompareDimensionStatCards view={view} />
        {/* Dimension-scoped triage: principles where one project sits far
            under the rest, and hard 30-day drops. Renders only when it has
            something to say. */}
        <CompareAttentionStrip
          ariaLabel={t('compare.dimAttentionAria', { dim: view.label })}
          noteText={t('compare.dimAttentionNote')}
          items={buildAttentionItems(dimAttention, onOpenProject, onOpenPrinciple)}
        />

        <div className="compare-lower compare-lower--dim">
          <CompareStandingsList
            view={view} activeId={activeId} setFocusId={setFocusId}
            onOpenProject={onOpenProject} onOpenProjectDimension={onOpenProjectDimension}
          />
          <CompareRadarPanel view={view} axes={axes} series={series} active={active} />
        </div>

        <PrincipleMatrix
          view={view} activeId={activeId} setFocusId={setFocusId}
          onOpenProject={onOpenProject} onOpenPrinciple={onOpenPrinciple}
        />

        <ComparePrincipleCards
          principles={view.principles} activeId={activeId} setFocusId={setFocusId} onOpenPrinciple={onOpenPrinciple}
        />
      </div>
    </>
  );
}
