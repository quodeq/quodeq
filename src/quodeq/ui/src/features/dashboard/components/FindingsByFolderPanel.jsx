/**
 * FindingsByFolderPanel: "where the findings live", one row per real folder,
 * most severe first. The prefix every finding shares is shown once in the
 * head instead of on every row; each row mutes its lead and keeps its last
 * two folders bright, trimming long paths from the left.
 */
import { useMemo, useState } from 'react';
import { GridTable, GridRow, GridCell, SectionLabel } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { groupByFolder, splitFolderLabel } from '../findingsGrouping.js';
import ListShowMore from './ListShowMore.jsx';
import { SeverityAndFilesCells } from './SeverityBadges.jsx';

export const FOLDERS_SHOWN = 8;

function FolderPath({ label }) {
  const { lead, tail } = splitFolderLabel(label);
  return (
    <span className="folder-path">
      <span className="folder-path__inner">
        <span className="folder-path__lead">{lead}</span>
        <span className="folder-path__tail">{tail || '/'}</span>
      </span>
    </span>
  );
}

export default function FindingsByFolderPanel({ dimensions, onFolderClick }) {
  const { prefix, rows } = useMemo(() => groupByFolder(dimensions), [dimensions]);
  const [open, setOpen] = useState(false);
  const fileCount = useMemo(() => rows.reduce((n, r) => n + r.fileCount, 0), [rows]);
  if (rows.length === 0) return null;
  const list = open ? rows : rows.slice(0, FOLDERS_SHOWN);
  return (
    <section className="qd-cards-panel folders-panel" aria-label={t('overview.foldersAria')}>
      <div className="qd-cards-panel__head">
        <SectionLabel>{t('overview.foldersLabel')}</SectionLabel>
        <span className="run-history-panel__stats">
          {prefix ? t('overview.foldersNoteIn', { prefix }) : t('overview.foldersNote')}
        </span>
      </div>
      <GridTable columns="minmax(0, 1fr) auto 48px" dense>
        {list.map((r) => (
          <GridRow key={r.dir} onClick={onFolderClick ? () => onFolderClick(r) : undefined}>
            <GridCell><span title={r.dir || '/'}><FolderPath label={r.label} /></span></GridCell>
            <SeverityAndFilesCells sev={r.sev} fileCount={r.fileCount} />
          </GridRow>
        ))}
      </GridTable>
      <div className="folders-panel__foot">
        {t('overview.foldersFoot', { folders: rows.length.toLocaleString(LOCALE), files: fileCount.toLocaleString(LOCALE) })}
      </div>
      <ListShowMore
        open={open} total={rows.length} shown={FOLDERS_SHOWN}
        allLabel={t('overview.showAllFolders', { count: rows.length.toLocaleString(LOCALE) })}
        onToggle={() => setOpen(!open)}
      />
    </section>
  );
}
