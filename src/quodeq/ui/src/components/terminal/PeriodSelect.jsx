import { t } from '../../strings/index.js';
/**
 * PeriodSelect — terminal-styled granularity selector for the score-history
 * chart. A native <select> (keyboard + a11y for free) re-skinned to the mono
 * terminal idiom, with a static caret. Options: Day / Week / Month.
 *
 * @param {object} props
 * @param {'day'|'week'|'month'} props.value
 * @param {(next: 'day'|'week'|'month') => void} props.onChange
 */
export default function PeriodSelect({ value, onChange }) {
  return (
    <span className="term-period-select-wrap">
      <select
        className="term-period-select"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        aria-label={t('common.groupHistoryBy')}
      >
        <option value="day">{t('common.periodDay')}</option>
        <option value="week">{t('common.periodWeek')}</option>
        <option value="month">{t('common.periodMonth')}</option>
      </select>
      <span className="term-period-select__caret" aria-hidden="true">▾</span>
    </span>
  );
}
