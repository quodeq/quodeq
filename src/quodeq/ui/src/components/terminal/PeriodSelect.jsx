import { t } from '../../strings/index.js';
import { GRANULARITY } from '../../utils/granularity.js';
import Select from '../select/Select.jsx';
/**
 * PeriodSelect — terminal-styled granularity selector for the score-history
 * chart, the app's Select in the mono terminal idiom. Options: Day / Week / Month.
 *
 * @param {object} props
 * @param {'day'|'week'|'month'} props.value
 * @param {(next: 'day'|'week'|'month') => void} props.onChange
 */
export default function PeriodSelect({ value, onChange }) {
  return (
    <span className="term-period-select-wrap">
      <Select
        className="term-period-select"
        value={value}
        onChange={(next) => onChange?.(next)}
        aria-label={t('common.groupHistoryBy')}
        options={[
          { value: GRANULARITY.DAY, label: t('common.periodDay') },
          { value: GRANULARITY.WEEK, label: t('common.periodWeek') },
          { value: GRANULARITY.MONTH, label: t('common.periodMonth') },
        ]}
      />
    </span>
  );
}
