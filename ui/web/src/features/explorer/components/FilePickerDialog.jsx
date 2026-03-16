import { useState } from 'react';

export default function FilePickerDialog({ files, selectedFile, onSelect, onClose }) {
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? files.filter((f) => f.toLowerCase().includes(search.trim().toLowerCase()))
    : files;

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="file-picker-title" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h3 id="file-picker-title">Select file</h3>
          <button type="button" className="dialog-close" onClick={onClose} aria-label="Close">&times;</button>
        </div>
        <input
          className="dialog-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search files..."
          aria-label="Search files"
          autoFocus
        />
        <ul className="file-picker-list" role="listbox">
          <li
            className={`file-picker-item ${!selectedFile ? 'active' : ''}`}
            role="option"
            aria-selected={!selectedFile}
            tabIndex={0}
            onClick={() => { onSelect(''); onClose(); }}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(''); onClose(); } }}
          >
            All files (no filter)
          </li>
          {filtered.map((file) => (
            <li
              key={file}
              className={`file-picker-item ${selectedFile === file ? 'active' : ''}`}
              role="option"
              aria-selected={selectedFile === file}
              tabIndex={0}
              onClick={() => { onSelect(file); onClose(); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(file); onClose(); } }}
            >
              {file}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="file-picker-empty">No files match &ldquo;{search}&rdquo;</li>
          )}
        </ul>
      </div>
    </div>
  );
}
