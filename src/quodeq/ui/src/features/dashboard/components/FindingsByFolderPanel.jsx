/**
 * FindingsByFolderPanel: "where the findings live", one row per real folder,
 * most severe first. The prefix every finding shares is shown once in the
 * head instead of on every row; each row mutes its lead and keeps its last
 * two folders bright, trimming long paths from the left. The list scrolls
 * inside the panel instead of opening and closing.
 */
import { useMemo } from 'react';
import { GridTable, GridRow, GridCell, SectionLabel } from '../../../components/terminal/index.js';
import { t, LOCALE } from '../../../strings/index.js';
import { groupByFolder, splitFolderLabel } from '../findingsGrouping.js';
import { SeverityAndFilesCells } from './SeverityBadges.jsx';

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
      {/* Every folder, scrolling inside the panel: beside the score history
          the list takes the chart's height, so neither panel ever grows. */}
      <div className="folders-panel__list">
      <GridTable columns="minmax(0, 1fr) auto 48px" dense>
        {rows.map((r) => (
          <GridRow key={r.dir} onClick={onFolderClick ? () => onFolderClick(r) : undefined}>
            <GridCell><span title={r.dir || '/'}><FolderPath label={r.label} /></span></GridCell>
            <SeverityAndFilesCells sev={r.sev} fileCount={r.fileCount} />
          </GridRow>
        ))}
      </GridTable>
      </div>
      <div className="folders-panel__foot">
        {t('overview.foldersFoot', { folders: rows.length.toLocaleString(LOCALE), files: fileCount.toLocaleString(LOCALE) })}
      </div>
    </section>
  );
}
