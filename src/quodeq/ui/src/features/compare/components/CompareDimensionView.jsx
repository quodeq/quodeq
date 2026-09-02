/**
 * CompareDimensionView — one dimension across every project in scope:
 * stat cards, ranked standings with per-principle bars, a radar overlaying
 * the leader / trailer / scope average (hovering a standings row overlays
 * that project too), and one card per principle.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { buildDimensionAttention } from '../compareModel.js';
import CompareMatrix from './CompareMatrix.jsx';
import CompareDimensionHeader from './CompareDimensionHeader.jsx';
import CompareDimensionStatCards from './CompareDimensionStatCards.jsx';
import CompareAttentionStrip from './CompareAttentionStrip.jsx';
import CompareStandingsList from './CompareStandingsList.jsx';
import CompareRadarPanel from './CompareRadarPanel.jsx';
import ComparePrincipleCards from './ComparePrincipleCards.jsx';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function buildAttentionItems(dimAttention, onOpenProject, onOpenPrinciple) {
  return dimAttention.map((item) => ({
    key: `${item.kind}-${item.name}-${item.principleLabel || ''}`,
    level: item.level,
    accentScore: item.kind === 'outlier' ? item.score : item.row.score,
    name: item.name,
    onNameClick: () => (item.kind === 'outlier'
      ? onOpenPrinciple?.(item.cell)
      : onOpenProject(item.row.id)),
    why: item.kind === 'outlier'
      ? [
        t('compare.dimReasonOutlier', { principle: item.principleLabel, score: score1(item.score) }),
        item.gap != null ? t('compare.dimReasonGap', { gap: score1(item.gap) }) : null,
      ].filter(Boolean).join(' · ')
      : t('compare.dimReasonDrop', { delta: score1(item.delta) }),
  }));
}

/** Radar series: average always shown, plus lead/trail, plus the hovered
 * standings row (recolored to focus instead of duplicated if it's already
 * plotted as lead/trail). */
function buildRadarSeries(view, focusId) {
  const byKey = (source) => view.principles.map((p) => {
    const found = source.principles.find((x) => x.key === p.key);
    return found ? found.score : null;
  });
  const focusStanding = focusId ? view.standings.find((s) => s.row.id === focusId) : null;
  const isFocused = (s) => Boolean(focusStanding && s === focusStanding);
  const extraFocus = focusStanding && focusStanding !== view.lead && focusStanding !== view.trail
    ? focusStanding
    : null;
  return [
    { values: view.principles.map((p) => p.avg), variant: 'average' },
    ...(view.trail && view.trail !== view.lead
      ? [{ values: byKey(view.trail), variant: 'trail', focused: isFocused(view.trail) }]
      : []),
    ...(view.lead ? [{ values: byKey(view.lead), variant: 'lead', focused: isFocused(view.lead) }] : []),
    ...(extraFocus ? [{ values: byKey(extraFocus), variant: 'focus' }] : []),
  ];
}

function buildDimensionMatrixRows(view, onOpenProject, onOpenPrinciple) {
  return view.standings.map((s) => ({
    id: s.row.id,
    name: s.row.name,
    remote: s.row.remote,
    overall: s.score,
    onOpenRow: () => onOpenProject(s.row.id),
    cells: Object.fromEntries(view.principles.map((p) => {
      const cell = p.perProject.find((x) => x.id === s.row.id);
      if (!cell) return [p.key, { score: null }];
      return [p.key, {
        score: cell.score,
        title: t('compare.openDimensionIn', { dim: p.label, project: s.row.name }),
        onClick: onOpenPrinciple ? () => onOpenPrinciple(cell) : undefined,
      }];
    })),
  }));
}

export default function CompareDimensionView({
  view, board, fleet, onOpenDimension, onOpenProject, onOpenPrinciple,
  onOpenProjectDimension,
}) {
  // The radar plots leader/trailer/average by default (all N polygons would
  // be unreadable); hovering a standings row overlays that project on top.
  const [focusId, setFocusId] = useState(null);
  const dimAttention = buildDimensionAttention(view);
  const axes = view.principles.map((p) => ({ label: p.label, value: p.avg }));
  const series = buildRadarSeries(view, focusId);

  return (
    <>
      <CompareDimensionHeader view={view} board={board} onOpenDimension={onOpenDimension} />
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
          view={view}
          onOpenProject={onOpenProject}
          onOpenProjectDimension={onOpenProjectDimension}
          setFocusId={setFocusId}
        />
        <CompareRadarPanel view={view} axes={axes} series={series} />
      </div>

      {/* v4c appendix: the same matrix grammar as the fleet's SCORE_MATRIX,
          one level deeper — projects x principles, cells opening that
          project's own principle page. */}
      <CompareMatrix
        ariaLabel={t('compare.principleMatrixAria', { dim: view.label })}
        header={t('compare.principleMatrixHeader', { rows: view.standings.length, cols: view.principles.length })}
        note={t('compare.matrixNote')}
        footOverall={view.avg}
        columns={view.principles.map((p) => ({ key: p.key, label: p.label, avg: p.avg }))}
        matrixRows={buildDimensionMatrixRows(view, onOpenProject, onOpenPrinciple)}
      />

      <ComparePrincipleCards principles={view.principles} onOpenPrinciple={onOpenPrinciple} />
    </>
  );
}
