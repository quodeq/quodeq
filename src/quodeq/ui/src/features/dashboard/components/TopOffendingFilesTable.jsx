// Props: { files, onFileClick }
// Terminal-styled tabular list of top offending files by violation count.
// Mirrors the TopFindings grid layout: column headers + dense rows.
// onFileClick is called with the file object when a row is clicked.

import { memo } from 'react';
import { GridTable, GridRow, GridCell, SevBadge } from '../../../components/terminal/index.js';

function basenameOf(filepath) {
  if (!filepath) return '';
  const idx = filepath.lastIndexOf('/');
  return idx >= 0 ? filepath.slice(idx + 1) : filepath;
}

function dirnameOf(filepath) {
  if (!filepath) return '';
  const idx = filepath.lastIndexOf('/');
  return idx >= 0 ? filepath.slice(0, idx) : '';
}

const TopOffendingFilesTable = memo(function TopOffendingFilesTable({ files, onFileClick }) {
  const list = files || [];
  if (list.length === 0) return null;

  return (
    <GridTable columns="minmax(0, 1fr) 64px 180px" dense>
      <GridRow header>
        <GridCell>FILE</GridCell>
        <GridCell align="right">N</GridCell>
        <GridCell>SEV</GridCell>
      </GridRow>

      {list.map((f, idx) => (
        <GridRow
          key={idx}
          onClick={onFileClick ? () => onFileClick(f) : undefined}
        >
          <GridCell>
            <div className="offending-file-cell">
              <span className="offending-file-name">{basenameOf(f.file)}</span>
              {dirnameOf(f.file) && (
                <span className="offending-file-path">{dirnameOf(f.file)}</span>
              )}
            </div>
          </GridCell>
          <GridCell numeric>{f.total}</GridCell>
          <GridCell>
            <span className="offending-file-tags">
              {f.critical > 0 && <SevBadge level="critical" count={f.critical} format="count-abbr" />}
              {f.major    > 0 && <SevBadge level="major"    count={f.major}    format="count-abbr" />}
              {f.minor    > 0 && <SevBadge level="minor"    count={f.minor}    format="count-abbr" />}
            </span>
          </GridCell>
        </GridRow>
      ))}
    </GridTable>
  );
});

export default TopOffendingFilesTable;
