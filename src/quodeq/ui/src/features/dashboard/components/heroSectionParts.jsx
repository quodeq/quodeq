/**
 * The pieces the two Overview hero strips share.
 *
 * The accumulated (project) hero and the run hero show the same four stats in
 * the same panel, and differ only in the score hint, the violations note and
 * the header above them. What is common lives here.
 */
import { withPending } from '../../../utils/pendingClass.js';
import { StatStrip, Stat } from '../../../components/terminal/index.js';
import { scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { HERO_CARD_KIND } from '../dashboardVocab.js';

/**
 * The hero panel: the section, its header row and the stat strip inside it.
 */
export function HeroPanel({ header, children, pending = false }) {
  return (
    <section className={withPending('acc-eval-panel acc-eval-panel--terminal', pending)} aria-busy={pending || undefined}>
      <div className="acc-eval-panel__top">{header}</div>
      <StatStrip cards>{children}</StatStrip>
    </section>
  );
}

const DENSITY_DECIMALS = 1;
const NO_VIOLATIONS_RATIO_PREFIX = '0:';

/**
 * The RATIO tile's value: "1:N" from complianceRatio, or "0:N" when there
 * are no violations at all (the shared helper's placeholder is for tables;
 * a tile never shows a bare dash).
 */
export function ratioDisplay(violations, compliance) {
  if (violations === 0) return `${NO_VIOLATIONS_RATIO_PREFIX}${compliance}`;
  return complianceRatio(violations, compliance);
}

/**
 * The fourth tile: RATIO as the number, with its reading on the first hint
 * line and, when the run recorded a files-read count, the density on a
 * second one. Without a density the tile is the ratio alone; nothing
 * renders as a dash.
 * @param {{ratio: string, density: number|null|undefined}} props
 */
export function RatioDensityStat({ ratio, density }) {
  const hasDensity = typeof density === 'number';
  return (
    <Stat
      label={t('overview.statRatio')}
      value={ratio}
      hint={(
        <>
          <span className="term-stat__hint-line">{t('overview.ratioHint')}</span>
          {hasDensity && (
            <span className="term-stat__hint-line">
              <b>{density.toFixed(DENSITY_DECIMALS)}</b> {t('overview.densityUnitHint')}
            </span>
          )}
        </>
      )}
    />
  );
}

/**
 * The two stats every hero strip ends with: the compliance count (clickable
 * when there is something to show) and the ratio tile, with the density
 * under it when the run has one.
 */
export function ComplianceAndRatioStats({ compliance, totalChecks, ratio, density, onCompliance, complianceAriaKey }) {
  return (
    <>
      <Stat
        label={t('overview.statCompliance')}
        value={compliance}
        hint={totalChecks > 0 ? t('overview.passingChecks', { count: totalChecks }) : null}
        onClick={onCompliance}
        ariaLabel={compliance > 0 ? t(complianceAriaKey) : undefined}
      />
      <RatioDensityStat ratio={ratio} density={density} />
    </>
  );
}

/**
 * The card-navigation handlers a hero strip wires up. A handler is left
 * undefined where there is nothing to navigate to, which is what makes that
 * card unclickable.
 *
 * @param {((target: string) => void)|undefined} onCardNavigate
 * @param {{violations: number, compliance: number}} counts
 * @returns {{handleViolations: Function|undefined, handleCompliance: Function|undefined, handleSeverity: Function|undefined}}
 */
export function heroCardHandlers(onCardNavigate, { violations, compliance }) {
  return {
    handleViolations: onCardNavigate && violations > 0 ? () => onCardNavigate(HERO_CARD_KIND.VIOLATIONS) : undefined,
    handleCompliance: onCardNavigate && compliance > 0 ? () => onCardNavigate(HERO_CARD_KIND.COMPLIANCE) : undefined,
    handleSeverity: onCardNavigate ? (level) => onCardNavigate(level) : undefined,
  };
}

/**
 * The SCORE stat both heroes open with: the number, then a row under it with
 * the grade chip and the trend badge (the accumulated hero's), laid out like
 * the severity chips under VIOLATIONS. `hint` adds a note after them.
 */
export function ScoreStat({ scoreDisplay, grade, extraTrailing = null, hint = null }) {
  return (
    <Stat
      label={t('overview.statScore')}
      value={scoreDisplay}
      hint={(
        <>
          <span className="acc-eval-sev-row">
            <GradeChip grade={grade} score={scoreDisplay} />
            {extraTrailing}
          </span>
          {hint}
        </>
      )}
    />
  );
}

/**
 * The grade as a chip next to the score value (EXEMPLARY, GOOD, ...), coloured
 * like the score, so the grade is read at a glance rather than in a hint.
 * @param {{grade: string|null|undefined, score: number|string|null}} props
 */
export function GradeChip({ grade, score }) {
  if (!grade) return null;
  return <span className={`chip small ${scoreColorClass(parseFloat(score))}`}>{String(grade).toUpperCase()}</span>;
}
