import { useState, useMemo } from 'react';
import { t } from '../../../strings/index.js';

function FilePickerList({ filtered, selectedFile, onSelect, onClose, search }) {
  return (
    <ul className="file-picker-list" role="listbox">
      <li
        className={`file-picker-item ${!selectedFile ? 'active' : ''}`}
        role="option"
        aria-selected={!selectedFile}
        tabIndex={0}
        onClick={() => { onSelect(''); onClose(); }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(''); onClose(); } }}
      >
        {t('explorer.allFilesNoFilter')}
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
        <li className="file-picker-empty">{t('explorer.noFilesMatch', { query: search })}</li>
      )}
    </ul>
  );
}

export default function FilePickerDialog({ files, selectedFile, onSelect, onClose }) {
  const [search, setSearch] = useState('');

  const needle = search.trim().toLowerCase();
  const filtered = useMemo(
    () => needle ? (files || []).filter((f) => f.toLowerCase().includes(needle)) : (files || []),
    [needle, files],
  );

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog-panel" role="dialog" aria-modal="true" aria-labelledby="file-picker-title" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h3 id="file-picker-title">{t('explorer.selectFileTitle')}</h3>
          <button type="button" className="dialog-close" onClick={onClose} aria-label={t('common.close')}>&times;</button>
        </div>
        <input
          className="dialog-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('explorer.searchFilesPlaceholder')}
          aria-label={t('explorer.searchFilesAria')}
          autoFocus
        />
        <FilePickerList filtered={filtered} selectedFile={selectedFile} onSelect={onSelect} onClose={onClose} search={search} />
      </div>
    </div>
  );
}
