// Props: { files, onFileClick, pageSize = 20 }
// Table of top offending files by violation count with pagination.
// onFileClick is called with the file object when a row is clicked.

import { memo, useState } from 'react';

const TopOffendingFilesTable = memo(function TopOffendingFilesTable({ files, onFileClick, pageSize = 20 }) {
  const [showAll, setShowAll] = useState(false);
  const displayFiles = showAll ? files : files.slice(0, pageSize);
  const hasMore = files.length > pageSize;

  return (
    <>
      <ul className="offending-file-list">
        {displayFiles.map((f, idx) => (
          <li
            key={idx}
            className={`offending-file-row${onFileClick ? ' offending-file-row--clickable' : ''}`}
            onClick={onFileClick ? () => onFileClick(f) : undefined}
            title={f.file}
          >
            <div className="offending-file-info">
              <span className="offending-file-path">{f.file}</span>
              {f.dimensionsStr && (
                <span className="offending-file-dims">{f.dimensionsStr}</span>
              )}
            </div>
            <strong className="offending-file-total">{f.total}</strong>
            <span className="offending-file-tags">
              {f.critical > 0 && (
                <span className="severity-tag critical">{f.critical} critical</span>
              )}
              {f.major > 0 && (
                <span className="severity-tag major">{f.major} major</span>
              )}
              {f.minor > 0 && (
                <span className="severity-tag minor">{f.minor} minor</span>
              )}
            </span>
            {onFileClick && <span className="offending-file-chevron">›</span>}
          </li>
        ))}
      </ul>
      {hasMore && (
        <button className="offending-show-more" onClick={() => setShowAll(v => !v)}>
          {showAll ? 'Show less' : `Show all ${files.length} files`}
        </button>
      )}
    </>
  );
});

export default TopOffendingFilesTable;
