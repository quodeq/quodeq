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
  return (
    <button
      type="button"
      className="verified-chip"
      title={`${verifiedCtx.noteFor(key) || 'Verified by the assistant'}. Click to remove the badge.`}
      onClick={(e) => {
        e.stopPropagation();
        verifiedCtx.unverify(v).catch(() => {});
      }}
    >
      verified
    </button>
  );
}
