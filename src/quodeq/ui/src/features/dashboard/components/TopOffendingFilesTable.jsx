// Props: { files, onFileClick }
// Terminal-styled list of top offending files by violation count.
// onFileClick is called with the file object when a row is clicked.
//
// Off-screen rows skip layout/paint via CSS `content-visibility: auto` on
// `.offending-file-row`, so the full list renders without a "Show all"
// pagination control.

import { memo } from 'react';
import { SevBadge } from '../../../components/terminal/index.js';

function basenameOf(filepath) {
  if (!filepath) return '';
  const idx = filepath.lastIndexOf('/');
  return idx >= 0 ? filepath.slice(idx + 1) : filepath;
}

const TopOffendingFilesTable = memo(function TopOffendingFilesTable({ files, onFileClick }) {
  const list = files || [];
  return (
    <ul className="offending-file-list">
      {list.map((f, idx) => (
        <li
          key={idx}
          className={`offending-file-row${onFileClick ? ' offending-file-row--clickable' : ''}`}
          onClick={onFileClick ? () => onFileClick(f) : undefined}
          role={onFileClick ? 'button' : undefined}
          tabIndex={onFileClick ? 0 : undefined}
          onKeyDown={onFileClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFileClick(f); } } : undefined}
          title={f.file}
        >
          <div className="offending-file-info">
            <span className="offending-file-name">{basenameOf(f.file)}</span>
            <span className="offending-file-path">{f.file}</span>
            {f.dimensionsStr && (
              <span className="offending-file-dims">{f.dimensionsStr}</span>
            )}
          </div>
          <strong className="offending-file-total">{f.total}</strong>
          <span className="offending-file-tags">
            {f.critical > 0 && <SevBadge level="critical" count={f.critical} format="count-abbr" />}
            {f.major > 0 && <SevBadge level="major" count={f.major} format="count-abbr" />}
            {f.minor > 0 && <SevBadge level="minor" count={f.minor} format="count-abbr" />}
          </span>
          {onFileClick && <span className="offending-file-chevron">›</span>}
        </li>
      ))}
    </ul>
  );
});

export default TopOffendingFilesTable;
