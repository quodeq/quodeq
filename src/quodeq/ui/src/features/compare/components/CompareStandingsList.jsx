import ComparePanel from './ComparePanel.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass, scoreGradeColorVar, complianceRatio } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t } from '../../../strings/index.js';
import { nf, score1, MIN_BAR_HEIGHT_PCT, SCORE_TO_PCT } from '../compareFormatters.js';


function standingTag(index, total, score, avg) {
  if (index === 0) return t('compare.tagLeads');
  if (index === total - 1) return t('compare.tagTrails');
  return score >= avg ? t('compare.tagAbove') : t('compare.tagBelow');
}

function StandingPBars({ s }) {
  return (
    <span className="compare-standings__pbars" aria-hidden="true">
      {s.principles.filter((p) => p.score != null).map((p) => (
        <span
          key={p.key}
          className="compare-standings__pbar"
          style={{
            height: `${Math.max(MIN_BAR_HEIGHT_PCT, Math.round(p.score * SCORE_TO_PCT))}%`,
            background: scoreGradeColorVar(p.score),
          }}
          title={`${p.label} · ${score1(p.score)}`}
        />
      ))}
    </span>
  );
}

function StandingScoreCells({ s }) {
  return (
    <>
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
    </>
  );
}

function StandingRow({ s, i, view, onOpenProject, onOpenProjectDimension, setFocusId }) {
  return (
    <li>
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
        <StandingScoreCells s={s} />
        <span className="compare-standings__viol">
          {t('compare.violCount', { count: nf(s.violations) })}
        </span>
        <span
          className="compare-standings__ratio"
          title={t('compare.ratioTip', { pass: nf(s.compliance), checks: nf(s.compliance + s.violations) })}
        >
          {complianceRatio(s.violations, s.compliance)}
        </span>
        <StandingPBars s={s} />
      </button>
    </li>
  );
}

export default function CompareStandingsList({ view, onOpenProject, onOpenProjectDimension, setFocusId }) {
  return (
    <ComparePanel ariaLabel={t('compare.standingsAria')} header={t('compare.standingsHeader', { count: view.standings.length })} note={t('compare.standingsNote', { dim: view.label })}>
      <ul className="compare-standings">
        {view.standings.map((s, i) => (
          <StandingRow
            key={s.row.id}
            s={s}
            i={i}
            view={view}
            onOpenProject={onOpenProject}
            onOpenProjectDimension={onOpenProjectDimension}
            setFocusId={setFocusId}
          />
        ))}
      </ul>
    </ComparePanel>
  );
}
