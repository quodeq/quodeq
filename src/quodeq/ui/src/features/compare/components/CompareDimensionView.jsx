/**
 * CompareDimensionView — one dimension across every project in scope:
 * stat cards, ranked standings with per-principle bars, a radar overlaying
 * the leader / trailer / scope average (hovering a standings row overlays
 * that project too), and one card per principle.
 */
import { Fragment, useState } from 'react';
import { TermHeader, StatStrip, Stat, SectionLabel } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass, scoreGradeColorVar, complianceRatio } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import { buildDimensionAttention } from '../compareModel.js';
import CompareRadar from './CompareRadar.jsx';
import CompareMatrix from './CompareMatrix.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function standingTag(index, total, score, avg) {
  if (index === 0) return t('compare.tagLeads');
  if (index === total - 1) return t('compare.tagTrails');
  return score >= avg ? t('compare.tagAbove') : t('compare.tagBelow');
}

function PrincipleDonut({ score }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const filled = c * Math.min(1, Math.max(0, (score ?? 0) / 10));
  return (
    <span className="compare-donut">
      <svg width="62" height="62" viewBox="0 0 62 62" aria-hidden="true">
        <circle className="compare-donut__track" cx="31" cy="31" r={r} />
        <circle
          className="compare-donut__fill"
          cx="31"
          cy="31"
          r={r}
          strokeDasharray={`${filled.toFixed(1)} ${(c - filled).toFixed(1)}`}
          transform="rotate(-90 31 31)"
          style={{ stroke: scoreGradeColorVar(score ?? 0) }}
        />
      </svg>
      <span className="compare-donut__value">{score1(score)}</span>
    </span>
  );
}

export default function CompareDimensionView({
  view, board, fleet, onOpenDimension, onOpenProject, onOpenPrinciple,
  onOpenProjectDimension,
}) {
  // The radar plots leader/trailer/average by default (all N polygons would
  // be unreadable); hovering a standings row overlays that project on top.
  const [focusId, setFocusId] = useState(null);
  // Everything here already qualified (outlier or hard drop), so the strip
  // caps at 3 like the fleet's and the rest waits behind the expand toggle.
  const [attnOpen, setAttnOpen] = useState(false);
  const dimAttention = buildDimensionAttention(view);
  const attnShown = attnOpen ? dimAttention : dimAttention.slice(0, 3);

  const axes = view.principles.map((p) => ({ label: p.label, value: p.avg }));
  const byKey = (source) => view.principles.map((p) => {
    const found = source.principles.find((x) => x.key === p.key);
    return found ? found.score : null;
  });
  const focusStanding = focusId
    ? view.standings.find((s) => s.row.id === focusId)
    : null;
  // When the hovered project is already plotted (leader/trailer), recolor
  // that polygon to the focus style instead of drawing a duplicate — the
  // hover must always visibly answer "which shape is this row".
  const isFocused = (s) => Boolean(focusStanding && s === focusStanding);
  const extraFocus = focusStanding && focusStanding !== view.lead && focusStanding !== view.trail
    ? focusStanding
    : null;
  const series = [
    { values: view.principles.map((p) => p.avg), variant: 'average' },
    ...(view.trail && view.trail !== view.lead
      ? [{ values: byKey(view.trail), variant: 'trail', focused: isFocused(view.trail) }]
      : []),
    ...(view.lead ? [{ values: byKey(view.lead), variant: 'lead', focused: isFocused(view.lead) }] : []),
    ...(extraFocus ? [{ values: byKey(extraFocus), variant: 'focus' }] : []),
  ];

  return (
    <>
      <div className="compare-page__top">
        {/* No local back button: the app breadcrumb (compare / <dimension>)
            already walks back, and the dimension tabs on the right switch
            sideways. */}
        <div className="compare-page__titles">
          <TermHeader
            name={view.label}
            sub={t('compare.dimSubtitle', {
              principles: view.principles.length,
              violations: nf(view.violations),
              projects: view.standings.length,
            })}
            badge={(
              <span className="compare-dim-badges">
                <span className={`compare-dim-tier ${scoreColorClass(view.avg)}`}>
                  {scoreToGradeLabel(view.avg) || ''}
                </span>
                <TrendBadge delta={view.delta} />
              </span>
            )}
          />
        </div>
        <div className="compare-header__controls">
          <span className="compare-sort" role="group" aria-label={t('compare.dimTabsAria')}>
            {board.map((b) => (
              <button
                key={b.key}
                type="button"
                className={`compare-sort__btn${b.key === view.key ? ' compare-sort__btn--on' : ''}`}
                onClick={() => onOpenDimension(b.key)}
              >
                {b.label.slice(0, 5)}
              </button>
            ))}
          </span>
        </div>
      </div>

      <StatStrip cards>
        <Stat
          label={t('compare.cardScopeScore')}
          value={score1(view.avg)}
          hint={`${scoreToGradeLabel(view.avg) || ''} · ${t('compare.projectsInScope', { count: view.standings.length })}`}
        />
        <Stat
          label={t('compare.cardSpread')}
          value={view.spread != null ? score1(view.spread) : '—'}
          hint={view.lead && view.trail && view.lead !== view.trail
            ? t('compare.spreadNote', {
              lead: view.lead.row.name,
              leadScore: score1(view.lead.score),
              trail: view.trail.row.name,
              trailScore: score1(view.trail.score),
            })
            : t('compare.needTwo')}
        />
        <Stat
          label={t('compare.cardViolations')}
          value={nf(view.violations)}
          hint={(
            <span className="compare-card__sev">
              <SevBadge level="critical" count={view.severity.critical} />
              <SevBadge level="major" count={view.severity.major} />
              <SevBadge level="minor" count={view.severity.minor} />
            </span>
          )}
        />
        <Stat
          label={t('compare.cardWeakest')}
          value={view.weakest ? view.weakest.label : '—'}
          hint={view.weakest ? t('compare.weakestNote', { score: score1(view.weakest.avg) }) : ''}
          tone={view.weakest && view.weakest.avg != null && view.weakest.avg < 5 ? 'critical' : 'default'}
        />
      </StatStrip>

      {/* Dimension-scoped triage: principles where one project sits far
          under the rest, and hard 30-day drops. Renders only when it has
          something to say. */}
      {dimAttention.length > 0 && (
        <section className="compare-panel" aria-label={t('compare.dimAttentionAria', { dim: view.label })}>
          <div className="compare-panel__head">
            <SectionLabel>{t('compare.attentionHeader', { count: dimAttention.length })}</SectionLabel>
            <span className="compare-panel__note">{t('compare.dimAttentionNote')}</span>
            {dimAttention.length > 3 && (
              <button
                type="button"
                className="compare-attention__toggle"
                onClick={() => setAttnOpen((v) => !v)}
              >
                {attnOpen
                  ? `${t('compare.attentionLess')} ▾`
                  : `${t('compare.attentionMore', { count: dimAttention.length - 3 })} ▸`}
              </button>
            )}
          </div>
          <div className="compare-attention compare-attention--strip">
            {attnShown.map((item, i) => (
              <Fragment key={`${item.kind}-${item.name}-${item.principleLabel || ''}`}>
                {/* Same boundary the standards list draws: the trio above
                    the line, the expanded rest dimmed below it. */}
                {i === 3 && <div className="compare-attention__divider" aria-hidden="true" />}
              <div
                className={`compare-attention__item compare-attention__item--${item.level}${i >= 3 ? ' compare-attention__item--rest' : ''}`}
                style={{ '--attention-accent': scoreGradeColorVar(item.kind === 'outlier' ? item.score : item.row.score) }}
              >
                <div className="compare-attention__top">
                  <button
                    type="button"
                    className="compare-attention__name"
                    onClick={() => (item.kind === 'outlier'
                      ? onOpenPrinciple?.(item.cell)
                      : onOpenProject(item.row.id))}
                  >
                    {item.name}
                  </button>
                  <span className={`compare-attention__level compare-attention__level--${item.level}`}>
                    {t(`compare.level${item.level.charAt(0).toUpperCase()}${item.level.slice(1)}`)}
                  </span>
                </div>
                <p className="compare-attention__why">
                  {item.kind === 'outlier'
                    ? [
                      t('compare.dimReasonOutlier', { principle: item.principleLabel, score: score1(item.score) }),
                      item.gap != null ? t('compare.dimReasonGap', { gap: score1(item.gap) }) : null,
                    ].filter(Boolean).join(' · ')
                    : t('compare.dimReasonDrop', { delta: score1(item.delta) })}
                </p>
              </div>
              </Fragment>
            ))}
          </div>
        </section>
      )}

      <div className="compare-lower compare-lower--dim">
        <section className="compare-panel" aria-label={t('compare.standingsAria')}>
          <div className="compare-panel__head">
            <SectionLabel>{t('compare.standingsHeader', { count: view.standings.length })}</SectionLabel>
            <span className="compare-panel__note">{t('compare.standingsNote', { dim: view.label })}</span>
          </div>
          <ul className="compare-standings">
            {view.standings.map((s, i) => (
              <li key={s.row.id}>
                <button
                  type="button"
                  className="compare-standings__row"
                  title={t('compare.openDimensionIn', { dim: view.label, project: s.row.name })}
                  // In a dimension context, a project opens ITS view of the
                  // same dimension (cross-project explorer entry), not its
                  // overview. Falls back to the overview if the run target
                  // is unknowable — and for remote rows, whose detail pages
                  // live behind the shared source, not local routes.
                  onClick={() => (s.runId && onOpenProjectDimension && !s.row.remote
                    ? onOpenProjectDimension({ id: s.row.id, source: s.row.source, runId: s.runId, dimName: s.dimName, dateLabel: s.dateLabel })
                    : onOpenProject(s.row.id))}
                  onMouseEnter={() => setFocusId(s.row.id)}
                  onMouseLeave={() => setFocusId(null)}
                  onFocus={() => setFocusId(s.row.id)}
                  onBlur={() => setFocusId(null)}
                >
                  <span className="compare-standings__rank">{i + 1}</span>
                  <span className="compare-standings__project">
                    <span className="compare-standings__name">{s.row.name}</span>
                    <span className="compare-standings__tag">
                      {standingTag(i, view.standings.length, s.score, view.avg)}
                    </span>
                  </span>
                  <span className="compare-standings__score">
                    <span className={scoreColorClass(s.score)}>{score1(s.score)}</span>
                    <span className="compare-standings__tier">{scoreToGradeLabel(s.score) || ''}</span>
                  </span>
                  <span className="compare-standings__delta">
                    {s.delta != null ? (
                      <TrendBadge delta={s.delta} />
                    ) : s.lastDelta != null ? (
                      <span className="compare-delta--old" title={t('compare.oldDeltaTip')}>
                        <TrendBadge delta={s.lastDelta} />
                      </span>
                    ) : null}
                  </span>
                  <span className="compare-standings__viol">
                    {t('compare.violCount', { count: nf(s.violations) })}
                  </span>
                  <span
                    className="compare-standings__ratio"
                    title={t('compare.ratioTip', { pass: nf(s.compliance), checks: nf(s.compliance + s.violations) })}
                  >
                    {complianceRatio(s.violations, s.compliance)}
                  </span>
                  <span className="compare-standings__pbars" aria-hidden="true">
                    {s.principles.filter((p) => p.score != null).map((p) => (
                      <span
                        key={p.key}
                        className="compare-standings__pbar"
                        style={{
                          height: `${Math.max(15, Math.round(p.score * 10))}%`,
                          background: scoreGradeColorVar(p.score),
                        }}
                        title={`${p.label} · ${score1(p.score)}`}
                      />
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="compare-panel" aria-label={t('compare.radialAria')}>
          <div className="compare-panel__head">
            <SectionLabel>{t('compare.radialHeader', { count: view.principles.length })}</SectionLabel>
            <span className="compare-panel__note">{t('compare.radialScale')}</span>
          </div>
          {view.principles.length >= 3 ? (
            <>
              <CompareRadar axes={axes} series={series} />
              <div className="compare-radar__legend">
                {view.lead && (
                  <span className="compare-radar__legendItem compare-radar__legendItem--lead">
                    {view.lead.row.name}
                  </span>
                )}
                {view.trail && view.trail !== view.lead && (
                  <span className="compare-radar__legendItem compare-radar__legendItem--trail">
                    {view.trail.row.name}
                  </span>
                )}
                <span className="compare-radar__legendItem compare-radar__legendItem--average">
                  {t('compare.legendAverage')}
                </span>
              </div>
            </>
          ) : (
            <p className="compare-panel__fallback">{t('compare.radialTooFew')}</p>
          )}
        </section>
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
        matrixRows={view.standings.map((s) => ({
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
        }))}
      />

      <section className="compare-panel" aria-label={t('compare.principlesAria')}>
        <div className="compare-panel__head">
          <SectionLabel>{t('compare.principlesHeader', { count: view.principles.length })}</SectionLabel>
          <span className="compare-panel__note">{t('compare.principlesNote')}</span>
        </div>
        <div className="compare-principles">
          {view.principles.map((p) => (
            <article key={p.key} className="compare-principle">
              <h3 className="compare-principle__name">{p.label}</h3>
              <div className="compare-principle__body">
                <PrincipleDonut score={p.avg} />
                <div className="compare-principle__facts">
                  {p.lead && (
                    <button
                      type="button"
                      className="compare-principle__lead"
                      title={t('compare.openPrincipleIn', { principle: p.label, project: p.lead.name })}
                      onClick={() => onOpenPrinciple?.(p.lead)}
                    >
                      ↑ {p.lead.name} {score1(p.lead.score)}
                    </button>
                  )}
                  {p.trail && (
                    <button
                      type="button"
                      className="compare-principle__trail"
                      title={t('compare.openPrincipleIn', { principle: p.label, project: p.trail.name })}
                      onClick={() => onOpenPrinciple?.(p.trail)}
                    >
                      ↓ {p.trail.name} {score1(p.trail.score)}
                    </button>
                  )}
                </div>
              </div>
              <div className="compare-principle__bars">
                {p.perProject.map((pp) => (
                  <button
                    key={pp.id}
                    type="button"
                    className="compare-principle__slot"
                    title={t('compare.openPrincipleIn', { principle: p.label, project: pp.name })}
                    aria-label={t('compare.openPrincipleIn', { principle: p.label, project: pp.name })}
                    onClick={() => onOpenPrinciple?.(pp)}
                  >
                    <span className="compare-principle__barTrack" aria-hidden="true">
                      <span
                        className="compare-principle__bar"
                        style={{
                          height: `${Math.max(15, Math.round(pp.score * 10))}%`,
                          background: scoreGradeColorVar(pp.score),
                        }}
                      />
                    </span>
                    <span className="compare-principle__rank" aria-hidden="true">{pp.rank}</span>
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

    </>
  );
}
