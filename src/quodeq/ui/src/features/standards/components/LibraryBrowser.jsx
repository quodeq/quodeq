import { useState } from 'react';
import { useLibrary } from '../hooks/useLibrary.js';

function LibraryCard({ standard, onImport, importing }) {
  const principleCount = standard.principles?.length ?? 0;
  const requirementCount = (standard.principles || []).reduce(
    (sum, p) => sum + (p.requirements?.length ?? 0),
    0
  );

  return (
    <div className="library-card">
      <div className="library-card-header">
        <h4 className="library-card-name">{standard.name}</h4>
        {standard.id && <span className="library-card-id">{standard.id}</span>}
      </div>
      {standard.description && (
        <p className="library-card-description">{standard.description}</p>
      )}
      <div className="library-card-counts">
        <span>{principleCount} {principleCount === 1 ? 'principle' : 'principles'}</span>
        <span className="library-card-counts-sep">·</span>
        <span>{requirementCount} {requirementCount === 1 ? 'requirement' : 'requirements'}</span>
      </div>
      <div className="library-card-footer">
        <button
          type="button"
          className="btn-primary library-import-btn"
          onClick={() => onImport(standard.file || standard.id)}
          disabled={importing}
        >
          Import
        </button>
      </div>
    </div>
  );
}

export default function LibraryBrowser({ onClose, onImported }) {
  const { libraryStandards, loading, error, importStandard } = useLibrary();
  const [importError, setImportError] = useState(null);

  const handleImport = async (file) => {
    try {
      setImportError(null);
      await importStandard(file);
      if (onImported) onImported();
      onClose();
    } catch (err) {
      console.error('Import failed:', err);
      setImportError(err.message || 'Import failed. Check the standard file and try again.');
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog modal-dialog--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Standards Library</h2>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <p className="library-browser-subtitle">
          Import community and reference standards into your workspace.
        </p>

        {loading && <div className="library-loading">Loading library...</div>}
        {(error || importError) && <p className="inline-error">{importError || error}</p>}

        {!loading && !error && libraryStandards.length === 0 && (
          <p className="library-empty">No community standards available.</p>
        )}

        {!loading && libraryStandards.length > 0 && (
          <div className="library-grid">
            {libraryStandards.map((s) => (
              <LibraryCard
                key={s.id || s.file}
                standard={s}
                onImport={handleImport}
                importing={false}
              />
            ))}
          </div>
        )}

        <div className="modal-actions modal-actions--end">
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
