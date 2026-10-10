/**
 * FixFirstPanel: the visible dimensions' requirements, most severe first.
 * A row opens the File page on that requirement's findings, the same live
 * selector the Violations page's By type view uses.
 */
import { useMemo, useState } from 'react';
import { GridTable, GridRow, GridCell, SectionLabel } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { groupByRequirement } from '../findingsGrouping.js';
import ListShowMore from './ListShowMore.jsx';
import { SeverityAndFilesCells } from './SeverityBadges.jsx';

export const FIX_FIRST_SHOWN = 8;

export default function FixFirstPanel({ dimensions, onRequirementClick }) {
  const rows = useMemo(() => groupByRequirement(dimensions), [dimensions]);
  const [open, setOpen] = useState(false);
  if (rows.length === 0) return null;
  const list = open ? rows : rows.slice(0, FIX_FIRST_SHOWN);
  return (
    <section className="qd-cards-panel fix-first-panel" aria-label={t('overview.fixFirstAria')}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.fixFirstLabel')} · {rows.length.toLocaleString(LOCALE)}</SectionLabel>
        <span className="run-history-panel__stats">{t('overview.fixFirstNote')}</span>
      </div>
      <GridTable columns="110px minmax(0, 1fr) auto 48px" dense>
        {list.map((r) => (
          <GridRow key={`${r.dimension}:${r.req}`} onClick={onRequirementClick ? () => onRequirementClick(r) : undefined}>
            <GridCell><span className="fix-first__req">{r.req}</span></GridCell>
            <GridCell>
              <div className="offending-file-cell">
                <span className="offending-file-name">{r.text}</span>
                <span className="offending-file-path">{r.principle ? `${r.dimension} · ${r.principle}` : r.dimension}</span>
              </div>
            </GridCell>
            <SeverityAndFilesCells sev={r.sev} fileCount={r.fileCount} />
          </GridRow>
        ))}
      </GridTable>
      <ListShowMore
        open={open} total={rows.length} shown={FIX_FIRST_SHOWN}
        allLabel={t('overview.showAllRequirements', { count: rows.length.toLocaleString(LOCALE) })}
        onToggle={() => setOpen(!open)}
      />
    </section>
  );
}
