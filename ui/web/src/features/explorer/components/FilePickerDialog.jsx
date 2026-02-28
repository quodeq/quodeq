import { useState } from 'react';

export default function FilePickerDialog({ files, selectedFile, onSelect, onClose }) {
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? files.filter((f) => f.toLowerCase().includes(search.trim().toLowerCase()))
    : files;

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h3>Select file</h3>
          <button type="button" className="dialog-close" onClick={onClose}>&times;</button>
        </div>
        <input
          className="dialog-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search files..."
          autoFocus
        />
        <ul className="file-picker-list">
          <li
            className={`file-picker-item ${!selectedFile ? 'active' : ''}`}
            onClick={() => { onSelect(''); onClose(); }}
          >
            All files (no filter)
          </li>
          {filtered.map((file) => (
            <li
              key={file}
              className={`file-picker-item ${selectedFile === file ? 'active' : ''}`}
              onClick={() => { onSelect(file); onClose(); }}
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
