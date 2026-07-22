import { useVerifiedFindings } from './verifiedFindingsContext.jsx';

/**
 * Shared verified-badge chip for any violation row.
 * Renders nothing when there is no VerifiedFindingsProvider in the tree
 * or when the finding has no badge. A failed unverify POST is swallowed
 * so it cannot produce an unhandled rejection.
 */
export function VerifiedChip({ v }) {
  const verifiedCtx = useVerifiedFindings();
  const key = `${v.req || ''}|${v.file || ''}|${v.line || 0}`;
  if (!verifiedCtx?.keys?.has(key)) return null;
  const note = verifiedCtx.noteFor(key);
  const icon = (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12" /></svg>
  );
  // Shared projects have no unverify route on the backend (mutation is
  // local-only by design, same as dismiss/restore/delete). Render the same
  // visual chip but as a plain, non-interactive span: no button role, no
  // onClick, no "Click to remove" copy — there is nothing to click into.
  if (verifiedCtx.readOnly) {
    const readOnlyLabel = note ? `Verified: ${note}` : 'Verified by the assistant';
    return (
      <span className="verified-chip verified-chip--readonly" title={readOnlyLabel} aria-label={readOnlyLabel}>
        {icon}
      </span>
    );
  }
  // Icon-only badge: a filled accent circle with a check (theme-aligned, not
  // a fixed blue). The tooltip carries the note; the aria-label always starts
  // with "Verified" so the control is named for assistive tech and tests.
  const hover = `${note || 'Verified by the assistant'}. Click to remove the badge.`;
  const label = note
    ? `Verified: ${note}. Click to remove the badge.`
    : 'Verified by the assistant. Click to remove the badge.';
  return (
    <button
      type="button"
      className="verified-chip"
      title={hover}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        verifiedCtx.unverify(v).catch(() => {});
      }}
    >
      {icon}
    </button>
  );
}
