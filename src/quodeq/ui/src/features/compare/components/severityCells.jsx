/**
 * The severity breakdowns the Compare tab repeats: three badges in
 * critical/major/minor order, in a card hint and in a table cell.
 */
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import { nf } from '../compareFormatters.js';

/** Critical/major/minor badges as a stat card's hint. */
export function SeverityCardHint({ severity }) {
  return (
    <span className="compare-card__sev">
      <SevBadge level="critical" count={severity.critical} />
      <SevBadge level="major" count={severity.major} />
      <SevBadge level="minor" count={severity.minor} />
    </span>
  );
}

/**
 * A table row's violations cell: the total, then the abbreviated severity
 * split (hidden by CSS on the narrow tiers).
 */
export function ViolationsCellBody({ total, severity }) {
  return (
    <>
      <span className="compare-row__violTotal">{nf(total)}</span>
      <span className="compare-row__sev">
        <SevBadge level="critical" format="count-abbr" count={severity.critical} />
        <SevBadge level="major" format="count-abbr" count={severity.major} />
        <SevBadge level="minor" format="count-abbr" count={severity.minor} />
      </span>
    </>
  );
}
