// Score-history bucket size: the stored preference (utils/scoreHistoryPrefs.js),
// PeriodSelect's options, the period bucketing in utils/dailyGrouping.js and
// utils/dateFormatting.js, and granularityLabel in strings/labels.js.
// A leaf module on purpose: tests that mock constants.js must not lose it.
export const GRANULARITY = Object.freeze({ DAY: 'day', WEEK: 'week', MONTH: 'month' });
