import { Fragment, useState } from 'react';
import { SectionLabel } from '../../../components/terminal/index.js';
import { scoreGradeColorVar } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';

function levelLabel(level) {
  return t(`compare.level${level.charAt(0).toUpperCase()}${level.slice(1)}`);
}

function CompareAttentionItem({ item, rest }) {
  return (
    <div
      className={`compare-attention__item compare-attention__item--${item.level}${rest ? ' compare-attention__item--rest' : ''}`}
      style={{ '--attention-accent': scoreGradeColorVar(item.accentScore) }}
    >
      <div className="compare-attention__top">
        <button
          type="button"
          className="compare-attention__name"
          onClick={item.onNameClick}
        >
          {item.name}
        </button>
        <span className={`compare-attention__level compare-attention__level--${item.level}`}>
          {levelLabel(item.level)}
        </span>
      </div>
      <p className="compare-attention__why">
        {item.why}
        {item.extra}
      </p>
    </div>
  );
}

/**
 * Needs-attention strip, shared by CompareFleetView (per-project rows) and
 * CompareDimensionView (per-principle-outlier / per-drop rows): always leads
 * with the top 3, the rest hides behind an expand toggle with a divider
 * between the always-on trio and the dimmed rest.
 *
 * Each caller normalizes its own item shape into
 * `{ key, level, accentScore, name, onNameClick, why, extra? }` — the two
 * variants disagree on what an item even IS (a project vs. an outlier/drop),
 * so only the wrapper, list, divider and toggle markup are shared; keep the
 * class names and aria-label wiring identical to both pre-split renders.
 */
export default function CompareAttentionStrip({ ariaLabel, noteText, items }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  const shown = open ? items : items.slice(0, 3);
  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.attentionHeader', { count: items.length })}</SectionLabel>
        <span className="compare-panel__note">{noteText}</span>
        {items.length > 3 && (
          <button
            type="button"
            className="compare-attention__toggle"
            onClick={() => setOpen((v) => !v)}
          >
            {open
              ? `${t('compare.attentionLess')} ▾`
              : `${t('compare.attentionMore', { count: items.length - 3 })} ▸`}
          </button>
        )}
      </div>
      <div className="compare-attention compare-attention--strip">
        {shown.map((item, i) => (
          <Fragment key={item.key}>
            {/* The standards list draws this same boundary: the always-on
                trio above the line, the expanded rest dimmed below it. */}
            {i === 3 && <div className="compare-attention__divider" aria-hidden="true" />}
            <CompareAttentionItem item={item} rest={i >= 3} />
          </Fragment>
        ))}
      </div>
    </section>
  );
}
