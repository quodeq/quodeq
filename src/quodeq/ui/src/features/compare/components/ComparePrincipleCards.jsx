import { SectionLabel } from '../../../components/terminal/index.js';
import { scoreGradeColorVar } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';

const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

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

function PrincipleBars({ p, onOpenPrinciple }) {
  return (
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
  );
}

function PrincipleCard({ p, onOpenPrinciple }) {
  return (
    <article className="compare-principle">
      <h3 className="compare-principle__name">{p.label}</h3>
      <div className="compare-principle__body">
        <PrincipleDonut score={p.avg} />
        <PrincipleFacts p={p} onOpenPrinciple={onOpenPrinciple} />
      </div>
      <PrincipleBars p={p} onOpenPrinciple={onOpenPrinciple} />
    </article>
  );
}

export default function ComparePrincipleCards({ principles, onOpenPrinciple }) {
  return (
    <section className="compare-panel" aria-label={t('compare.principlesAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.principlesHeader', { count: principles.length })}</SectionLabel>
        <span className="compare-panel__note">{t('compare.principlesNote')}</span>
      </div>
      <div className="compare-principles">
        {principles.map((p) => (
          <PrincipleCard key={p.key} p={p} onOpenPrinciple={onOpenPrinciple} />
        ))}
      </div>
    </section>
  );
}
