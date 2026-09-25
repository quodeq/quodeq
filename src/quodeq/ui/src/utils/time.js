// Unit conversions for date math. Every "days between" or "N days ago"
// computation divides or multiplies by these instead of spelling out
// 86400000 or 3600. No imports of its own: constants.js and every other
// module that needs a time factor imports from here, never the reverse.
export const MS_PER_SECOND = 1000; // ms in a second
export const SECONDS_PER_MINUTE = 60; // seconds in a minute
export const MINUTES_PER_HOUR = 60; // minutes in an hour
export const HOURS_PER_DAY = 24; // hours in a day

export const SECONDS_PER_HOUR = MINUTES_PER_HOUR * SECONDS_PER_MINUTE; // seconds in an hour
export const MS_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR * SECONDS_PER_MINUTE * MS_PER_SECOND; // ms in a day
