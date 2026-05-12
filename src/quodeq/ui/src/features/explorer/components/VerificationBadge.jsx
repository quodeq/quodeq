const VERDICT_LABELS = {
  false_positive: 'False positive',
  confirmed: 'Confirmed',
  inconclusive: 'Inconclusive',
  not_applicable: 'Not applicable',
};

// Single-character marks chosen to convey the verdict without depending on
// color (the severity pill already uses color heavily on the same row).
const VERDICT_MARKS = {
  false_positive: '✓',
  confirmed: '!',
  inconclusive: '?',
  not_applicable: 'i',
};

/**
 * Render a small badge for the verifier's verdict next to a finding row.
 * Renders nothing when no verification record is available.
 *
 * @param {object} props
 * @param {{verdict: string, confidence: number} | null | undefined} props.verification
 */
export function VerificationBadge({ verification }) {
  if (!verification || !verification.verdict) return null;
  const { verdict, confidence } = verification;
  const label = VERDICT_LABELS[verdict] || verdict;
  const mark = VERDICT_MARKS[verdict] || '·';
  const showPct =
    verdict !== 'not_applicable' &&
    typeof confidence === 'number' &&
    confidence > 0;
  return (
    <span
      className={`vrow-verdict vrow-verdict--${verdict}`}
      title={`Verifier verdict: ${label}`}
    >
      <span className="vrow-verdict-mark" aria-hidden="true">{mark}</span>
      <span className="vrow-verdict-label">{label}</span>
      {showPct && (
        <span className="vrow-verdict-pct">
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
}
