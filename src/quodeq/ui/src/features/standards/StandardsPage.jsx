import { useState } from 'react';
import { useStandards } from './hooks/useStandards.js';
import { useVisibleStandards } from './hooks/useVisibleStandards.js';
import StandardsList from './components/StandardsList.jsx';
import StandardEditor from './components/StandardEditor.jsx';
import LibraryBrowser from './components/LibraryBrowser.jsx';
import ImportModal from './components/ImportModal.jsx';

function useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible) {
  const [view, setView] = useState({ mode: 'list' });
  const [showLibrary, setShowLibrary] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const handleEdit = (standardId) => setView({ mode: 'edit', standardId });
  const handleNewStandard = () => setView({ mode: 'new' });
  const handleEditorBack = () => { setView({ mode: 'list' }); refresh(); };
  const handleSaved = (savedId) => { if (savedId) addVisible(savedId); setView({ mode: 'list' }); refresh(); };
  const handleDeleteWithCleanup = async (id) => { removeVisible(id); await handleDelete(id); };

  return { view, showLibrary, setShowLibrary, showImport, setShowImport, handleEdit, handleNewStandard, handleEditorBack, handleSaved, handleDeleteWithCleanup };
}

function StandardsListView({ grouped, loading, error, actions }) {
  return (
    <>
      {error && <p className="inline-error" style={{ marginBottom: 16 }}>{error}</p>}
      {loading ? (
        <div className="standards-loading">Loading standards...</div>
      ) : (
        <StandardsList grouped={grouped} actions={actions} />
      )}
    </>
  );
}

export default function StandardsPage() {
  const { grouped, loading, error, refresh, handleDelete, handleDuplicate } = useStandards();
  const { isVisible, toggle, add: addVisible, remove: removeVisible } = useVisibleStandards();
  const { view, showLibrary, setShowLibrary, showImport, setShowImport, handleEdit, handleNewStandard, handleEditorBack, handleSaved, handleDeleteWithCleanup } = useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible);

  if (view.mode === 'edit' || view.mode === 'new') {
    return <StandardEditor standardId={view.standardId} isNew={view.mode === 'new'} onBack={handleEditorBack} onSaved={handleSaved} />;
  }

  return (
    <div className="standards-page">
      <div className="standards-page-header">
        <div>
          <h1 className="standards-page-title">Standards</h1>
          <p className="standards-page-subtitle">Manage evaluation standards and quality criteria.</p>
        </div>
        <div className="standards-page-header-actions">
          <button type="button" className="btn-secondary" onClick={() => setShowImport(true)}>Import</button>
          <button type="button" className="btn-primary" onClick={handleNewStandard}>+ New Standard</button>
        </div>
      </div>
      <StandardsListView grouped={grouped} loading={loading} error={error} actions={{ onEdit: handleEdit, onDelete: handleDeleteWithCleanup, onDuplicate: handleDuplicate, isVisible, onToggleVisibility: toggle }} />
      {showLibrary && <LibraryBrowser onClose={() => setShowLibrary(false)} onImported={() => { setShowLibrary(false); refresh(); }} />}
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={() => { setShowImport(false); refresh(); }} />}
    </div>
  );
}
