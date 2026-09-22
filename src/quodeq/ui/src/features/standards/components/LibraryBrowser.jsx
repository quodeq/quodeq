import { useState } from 'react';
import { useLibrary } from '../hooks/useLibrary.js';
import { t } from '../../../strings/index.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

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
        <span>{principleCount === 1 ? t('standards.principlesCountOne', { count: principleCount }) : t('standards.principlesCountMany', { count: principleCount })}</span>
        <span className="library-card-counts-sep">·</span>
        <span>{requirementCount === 1 ? t('standards.requirementsCountOne', { count: requirementCount }) : t('standards.requirementsCountMany', { count: requirementCount })}</span>
      </div>
      <div className="library-card-footer">
        <button
          type="button"
          className="btn-primary library-import-btn"
          onClick={() => onImport(standard.file || standard.id)}
          disabled={importing}
        >
          {t('standards.importBtn')}
        </button>
      </div>
    </div>
  );
}

function LibraryModalHeader({ onClose }) {
  return (
    <div className="modal-header">
      <h2 className="modal-title">{t('standards.libraryTitle')}</h2>
      <button type="button" className="modal-close-btn" onClick={onClose} aria-label={t('common.close')}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

function LibraryGrid({ loading, error, libraryStandards, handleImport }) {
  if (loading) return null;
  if (!error && libraryStandards.length === 0) {
    return <p className="library-empty">{t('standards.noCommunityStandards')}</p>;
  }
  if (libraryStandards.length === 0) return null;
  return (
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
      setImportError(apiErrorMessage(err, 'standards.importFailedRetry'));
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog modal-dialog--wide" onClick={(e) => e.stopPropagation()}>
        <LibraryModalHeader onClose={onClose} />

        <p className="library-browser-subtitle">
          {t('standards.librarySubtitle')}
        </p>

        {loading && <div className="library-loading">{t('standards.loadingLibrary')}</div>}
        {(error || importError) && <p className="inline-error">{importError || error}</p>}

        <LibraryGrid loading={loading} error={error} libraryStandards={libraryStandards} handleImport={handleImport} />

        <div className="modal-actions modal-actions--end">
          <button type="button" className="btn-secondary" onClick={onClose}>{t('common.close')}</button>
        </div>
      </div>
    </div>
  );
}
