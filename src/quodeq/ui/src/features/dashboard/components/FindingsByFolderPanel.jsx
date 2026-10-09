/**
 * FindingsByFolderPanel: "where the findings live", one row per real folder,
 * most severe first. The prefix every finding shares is shown once in the
 * head instead of on every row. Each row reads like a file row: its last two
 * folders on top, the folders above them underneath, small and quiet, trimmed
 * from the left when long. The panel shows the top few, which fit beside the
 * score history; every folder is one click away in the Map tab, the tree of
 * the whole codebase.
 */
import { useMemo } from 'react';

// Two-line rows: five sit beside the score history chart without a scroll.
export const FOLDERS_SHOWN = 5;
import { GridTable, GridRow, GridCell, SectionLabel } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { groupByFolder, splitFolderLabel } from '../findingsGrouping.js';
import { SeverityAndFilesCells } from './SeverityBadges.jsx';

/** The folder on top, bright; the folders above it below, small and quiet. */
function FolderPath({ label }) {
  const { lead, tail } = splitFolderLabel(label);
  return (
    <div className="offending-file-cell folder-path">
      <span className="offending-file-name">{tail || '/'}</span>
      {lead && <span className="folder-path__lead"><span className="folder-path__inner">{lead}</span></span>}
    </div>
  );
}

export default function FindingsByFolderPanel({ dimensions, onFolderClick, onOpenMap }) {
  const { prefix, rows } = useMemo(() => groupByFolder(dimensions), [dimensions]);
  const fileCount = useMemo(() => rows.reduce((n, r) => n + r.fileCount, 0), [rows]);
  if (rows.length === 0) return null;
  return (
    <section className="qd-cards-panel folders-panel" aria-label={t('overview.foldersAria')}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.foldersLabel')}</SectionLabel>
        <span className="run-history-panel__stats">
          {prefix ? t('overview.foldersNoteIn', { prefix }) : t('overview.foldersNote')}
        </span>
      </div>
      <GridTable columns="minmax(0, 1fr) auto 48px" dense>
        {rows.slice(0, FOLDERS_SHOWN).map((r) => (
          <GridRow key={r.dir} onClick={onFolderClick ? () => onFolderClick(r) : undefined}>
            <GridCell><div title={r.dir || '/'}><FolderPath label={r.label} /></div></GridCell>
            <SeverityAndFilesCells sev={r.sev} fileCount={r.fileCount} />
          </GridRow>
        ))}
      </GridTable>
      <div className="panel-foot">
        <span>{t('overview.foldersFoot', { folders: rows.length.toLocaleString(LOCALE), files: fileCount.toLocaleString(LOCALE) })}</span>
        {onOpenMap && rows.length > FOLDERS_SHOWN && (
          <button type="button" className="panel-foot__link" onClick={onOpenMap}>{t('overview.foldersOpenMap')}</button>
        )}
      </div>
    </section>
  );
}
