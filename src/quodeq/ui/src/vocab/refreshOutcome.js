// Mirror of src/quodeq/core/types/working_copy_refresh.py:RefreshOutcome.
// UPDATED and UP_TO_DATE are successes; every other member is a refusal,
// which arrives as an error whose `code` is the member's name.
export const REFRESH_OUTCOME = Object.freeze({
  UPDATED: 'updated', UP_TO_DATE: 'up_to_date', NOT_REFRESHABLE: 'not_refreshable', BUSY: 'busy',
  DIRTY: 'dirty', NO_UPSTREAM: 'no_upstream', DIVERGED: 'diverged', FETCH_FAILED: 'fetch_failed',
});
