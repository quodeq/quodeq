/** The class a section wears while its data is being refetched behind the
 * values it still shows (a sweeping line, muted text; see dashboard.css). */
export const SECTION_PENDING_CLASS = 'section-pending';

/** Append the pending class to a base class list when `pending` is true. */
export function withPending(base, pending) {
  return pending ? `${base} ${SECTION_PENDING_CLASS}` : base;
}
