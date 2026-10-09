/**
 * Needs attention, as a ranked to-do list beside the direction map: each
 * project with its level, score, short reason tags (weakest dimension,
 * decline, staleness, coverage) and a link to its weakest dimension.
 * Ranked by consequence (low score x size x staleness, buildAttention).
 * Hovering a row lights the project up across the page.
 */
import { t } from '../../../strings/index.js';
import { scoreColorClass } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import { REASON_TYPE } from '../compareBoard.js';
import { nf, score1 } from '../compareFormatters.js';

function reasonText(r) {
  if (r.type === REASON_TYPE.WORST_DIM) return t('compare.reasonWorstDim', { dim: r.dim, score: score1(r.score) });
  if (r.type === REASON_TYPE.DECLINING) return t('compare.reasonDeclining', { delta: r.delta });
  if (r.type === REASON_TYPE.STALE) {
    return r.commits != null ? t('compare.reasonStaleCommits', { count: nf(r.commits) }) : t('compare.reasonStale');
  }
  if (r.type === REASON_TYPE.COVERAGE) return t('compare.reasonCoverage', { pct: r.pct });
  return null;
}

export default function CompareAttentionList({ items, hover, setHover, onOpenProject, openDimension }) {
  return (
    <ComparePanel
      ariaLabel={t('compare.attentionAria')}
      header={t('compare.attentionHeader', { count: items.length })}
      note={t('compare.attentionNote')}
    >
      {items.length === 0 ? <p className="compare-panel__fallback">{t('compare.attentionEmpty')}</p> : (
        <ol className="compare-attnlist">
          {items.map(({ row, level, reasons, worstDim }) => (
            <li
              key={row.id}
              className={`compare-attnlist__item${hover === row.id ? ' is-on' : ''}`}
              onMouseEnter={() => setHover(row.id)}
              onMouseLeave={() => setHover(null)}
            >
              <span className={`compare-attnlist__level compare-attnlist__level--${level}`} title={t(`compare.level${level.charAt(0).toUpperCase()}${level.slice(1)}`)} />
              <button type="button" className="compare-attnlist__name" onClick={() => onOpenProject(row.id)}>{row.name}</button>
              <span className={`compare-attnlist__score ${scoreColorClass(row.score)}`}>{score1(row.score)}</span>
              <span className="compare-attnlist__tags">
                {reasons.map((r) => reasonText(r)).filter(Boolean).map((text) => <span key={text} className="compare-attnlist__tag">{text}</span>)}
              </span>
              {worstDim && (
                <button type="button" className="compare-attnlist__link" onClick={() => openDimension(worstDim)}>
                  {t('compare.openDimensionGo', { dim: worstDim })}
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </ComparePanel>
  );
}
