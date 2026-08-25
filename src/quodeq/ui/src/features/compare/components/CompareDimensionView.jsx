/**
 * CompareDimensionView — one dimension across every project in scope:
 * stat cards, ranked standings with per-principle bars, a radar overlaying
 * the leader / trailer / scope average, and one card per principle.
 */
import { StatStrip, Stat, SectionLabel } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import CompareRadar from './CompareRadar.jsx';

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
  view, board, fleet, onBack, onOpenDimension, onOpenProject,
}) {
  const axes = view.principles.map((p) => ({ label: p.label, value: p.avg }));
  const byKey = (source) => view.principles.map((p) => {
    const found = source.principles.find((x) => x.key === p.key);
    return found ? found.score : null;
  });
  const series = [
    { values: view.principles.map((p) => p.avg), variant: 'average' },
    ...(view.trail && view.trail !== view.lead
      ? [{ values: byKey(view.trail), variant: 'trail' }]
      : []),
    ...(view.lead ? [{ values: byKey(view.lead), variant: 'lead' }] : []),
  ];

  return (
    <>
      <header className="compare-header compare-header--dim">
        <div className="compare-header__titles">
          <button type="button" className="compare-back" onClick={onBack}>
            ‹ {t('compare.backToFleet')}
          </button>
          <div className="compare-dim-title">
            <h1 className="compare-title">{view.label}</h1>
            <span className={`compare-dim-tier ${scoreColorClass(view.avg)}`}>
              {scoreToGradeLabel(view.avg) || ''}
            </span>
            <TrendBadge delta={view.delta} />
          </div>
          <p className="compare-subtitle">
            {t('compare.dimSubtitle', {
              principles: view.principles.length,
              violations: nf(view.violations),
              projects: view.standings.length,
            })}
          </p>
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
      </header>

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
                  onClick={() => onOpenProject(s.row.id)}
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
                    <span className="compare-principle__lead">
                      ↑ {p.lead.name} {score1(p.lead.score)}
                    </span>
                  )}
                  {p.trail && (
                    <span className="compare-principle__trail">
                      ↓ {p.trail.name} {score1(p.trail.score)}
                    </span>
                  )}
                </div>
              </div>
              <div className="compare-principle__bars" aria-hidden="true">
                {p.perProject.map((pp) => (
                  <span
                    key={pp.id}
                    className="compare-principle__bar"
                    style={{
                      height: `${Math.max(15, Math.round(pp.score * 10))}%`,
                      background: scoreGradeColorVar(pp.score),
                    }}
                    title={`${pp.name} · ${score1(pp.score)}`}
                  />
                ))}
              </div>
              <p className="compare-principle__caption">{t('compare.barPerProject')}</p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
