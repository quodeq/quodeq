/**
 * The fairness strip under the verdict: is this an apples-to-apples
 * comparison? Each check from comparabilityChecks() renders as a muted ✓
 * when it holds and a caution when it weakens the comparison.
 */
import { t } from '../../../strings/index.js';
import { DUEL_CHECK, comparabilityChecks } from '../compareDuelAnalysis.js';
import { nf } from '../compareFormatters.js';

function scanGapText({ days }) {
  if (days == null) return t('compare.duelCheckScanUnknown');
  if (days === 0) return t('compare.duelCheckSameDay');
  return t('compare.duelCheckScanGap', { days: nf(days) });
}

function sizeText({ a, b, langA, langB }) {
  const files = t('compare.duelCheckSize', { a: nf(a ?? 0), b: nf(b ?? 0) });
  return langA && langB ? `${files} · ${t('compare.duelCheckLang', { a: langA, b: langB })}` : files;
}

const TEXT = Object.freeze({
  [DUEL_CHECK.DIMENSIONS]: (p) => t('compare.duelCheckDimensions', p),
  [DUEL_CHECK.SCAN_GAP]: scanGapText,
  [DUEL_CHECK.COMMITS]: (p) => t('compare.duelCheckCommits', { name: p.name, count: nf(p.count) }),
  [DUEL_CHECK.SIZE]: sizeText,
  [DUEL_CHECK.COVERAGE]: (p) => t('compare.duelCheckCoverage', p),
});

export default function CompareDuelChecks({ duel }) {
  const checks = comparabilityChecks(duel);
  return (
    <ul className="compare-duel-checks" aria-label={t('compare.duelChecksAria')}>
      {checks.map((c) => {
        const text = TEXT[c.key](c.params);
        return (
          <li key={`${c.key}:${text}`} className={`compare-duel-checks__item${c.ok ? '' : ' compare-duel-checks__item--warn'}`}>
            <span className="compare-duel-checks__mark" aria-hidden="true">{c.ok ? '✓' : '!'}</span>
            {!c.ok && <span className="sr-only">{t('compare.duelCheckCaution')}</span>}
            {text}
          </li>
        );
      })}
    </ul>
  );
}
