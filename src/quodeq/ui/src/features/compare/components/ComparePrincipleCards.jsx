import ComparePanel from './ComparePanel.jsx';
import { scoreGradeColorVar } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { score1, MIN_BAR_HEIGHT_PCT, SCORE_TO_PCT } from '../compareFormatters.js';
import { SCORE_SCALE_MAX } from '../../../constants.js';


function PrincipleDonut({ score }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const filled = c * Math.min(1, Math.max(0, (score ?? 0) / SCORE_SCALE_MAX));
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

function PrincipleFacts({ p, onOpenPrinciple }) {
  return (
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
  );
}

/** Ranked bars, one per project in standings order. The view's active
 * project (hovered anywhere, else the app's selection) keeps full colour
 * while the rest fade, and hovering a bar makes that project active. A
 * dashed tick across the bars marks the scope average. */
function PrincipleBars({ p, activeId, setFocusId, onOpenPrinciple }) {
  const avgPct = p.avg == null ? null : Math.round(p.avg * SCORE_TO_PCT);
  return (
    <div
      className={`compare-principle__bars${activeId ? ' has-active' : ''}`}
      onMouseLeave={setFocusId ? () => setFocusId(null) : undefined}
    >
      {p.perProject.map((pp) => (
        <button
          key={pp.id}
          type="button"
          className={`compare-principle__slot${pp.id === activeId ? ' is-active' : ''}`}
          title={t('compare.openPrincipleIn', { principle: p.label, project: pp.name })}
          aria-label={t('compare.openPrincipleIn', { principle: p.label, project: pp.name })}
          onClick={() => onOpenPrinciple?.(pp)}
          onMouseEnter={setFocusId ? () => setFocusId(pp.id) : undefined}
          onFocus={setFocusId ? () => setFocusId(pp.id) : undefined}
          onBlur={setFocusId ? () => setFocusId(null) : undefined}
        >
          <span className="compare-principle__barTrack" aria-hidden="true">
            {avgPct != null && (
              <span className="compare-principle__avgTick" style={{ bottom: `${avgPct}%` }} />
            )}
            <span
              className="compare-principle__bar"
              style={{
                height: `${Math.max(MIN_BAR_HEIGHT_PCT, Math.round(pp.score * SCORE_TO_PCT))}%`,
                background: scoreGradeColorVar(pp.score),
              }}
            />
          </span>
          <span className="compare-principle__rank" aria-hidden="true">{pp.rank}</span>
        </button>
      ))}
    </div>
  );
}

/** The active project's score on this principle, named so the bar row can
 * be read without a tooltip. A dash when it has no score here. */
function PrincipleActiveLine({ p, activeId }) {
  const pp = activeId ? p.perProject.find((x) => x.id === activeId) : null;
  if (!pp) return null;
  return (
    <div className="compare-principle__active">
      <span className="compare-principle__activeName">{pp.name}</span>
      <span className="compare-principle__activeScore">{pp.score == null ? '—' : score1(pp.score)}</span>
    </div>
  );
}

function PrincipleCard({ p, activeId, setFocusId, onOpenPrinciple }) {
  return (
    <article className="compare-principle">
      <h3 className="compare-principle__name">{p.label}</h3>
      <div className="compare-principle__body">
        <PrincipleDonut score={p.avg} />
        <PrincipleFacts p={p} onOpenPrinciple={onOpenPrinciple} />
      </div>
      <PrincipleBars p={p} activeId={activeId} setFocusId={setFocusId} onOpenPrinciple={onOpenPrinciple} />
      <PrincipleActiveLine p={p} activeId={activeId} />
    </article>
  );
}

/** `activeId` / `setFocusId` tie the cards into the dimension view's one
 * active project; both are optional so the cards also render standalone. */
export default function ComparePrincipleCards({ principles, activeId = null, setFocusId = null, onOpenPrinciple }) {
  return (
    <ComparePanel ariaLabel={t('compare.principlesAria')} header={t('compare.principlesHeader', { count: principles.length })} note={t('compare.principlesNote')}>
      <div className="compare-principles">
        {principles.map((p) => (
          <PrincipleCard key={p.key} p={p} activeId={activeId} setFocusId={setFocusId} onOpenPrinciple={onOpenPrinciple} />
        ))}
      </div>
    </ComparePanel>
  );
}
