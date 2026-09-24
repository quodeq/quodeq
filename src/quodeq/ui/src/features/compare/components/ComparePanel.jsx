import { SectionLabel } from '../../../components/terminal/index.js';

/**
 * The frame every compare panel sits in: a labelled section with a heading
 * row (label, note, optional trailing controls) above the panel body.
 */
export default function ComparePanel({ ariaLabel, header, note, headExtra = null, children }) {
  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{header}</SectionLabel>
        <span className="compare-panel__note">{note}</span>
        {headExtra}
      </div>
      {children}
    </section>
  );
}
