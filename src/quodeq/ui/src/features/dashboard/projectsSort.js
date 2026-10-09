/**
 * How the Repositories table sorts. The column headers set it (see
 * ProjectsTableHead); it lives in the nav entry's filters next to the query
 * and location, as `sort` and `dir`.
 */
export const SORT_KEY = Object.freeze({ ACTIVITY: 'activity', NAME: 'name', SCORE: 'score', FILES: 'files' });
export const SORT_DIR = Object.freeze({ ASC: 'asc', DESC: 'desc' });

// The direction a column starts in: names A to Z, everything else biggest
// or newest first.
const NATURAL_DIR = { [SORT_KEY.NAME]: SORT_DIR.ASC };

export function naturalDirection(key) {
  return NATURAL_DIR[key] ?? SORT_DIR.DESC;
}

/** The direction `key` sorts in now: the stored one when it is the active column. */
export function sortDirection(filters, key) {
  const active = (filters?.sort ?? SORT_KEY.ACTIVITY) === key;
  return active && filters?.dir ? filters.dir : naturalDirection(key);
}

/** The filters patch for a header click: a new column starts natural, the active one flips. */
export function nextSort(filters, key) {
  const active = (filters?.sort ?? SORT_KEY.ACTIVITY) === key;
  if (!active) return { sort: key, dir: naturalDirection(key) };
  return { sort: key, dir: sortDirection(filters, key) === SORT_DIR.ASC ? SORT_DIR.DESC : SORT_DIR.ASC };
}
