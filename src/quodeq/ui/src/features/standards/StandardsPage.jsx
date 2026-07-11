import { useState } from 'react';
import { useStandards } from './hooks/useStandards.js';
import { useVisibleStandards } from './hooks/useVisibleStandards.js';
import { useStandardsOverrides } from './hooks/useStandardsOverrides.js';
import StandardsTable from './components/StandardsTable.jsx';
import StandardEditor from './components/StandardEditor.jsx';
import ImportModal from './components/ImportModal.jsx';
import { TermHeader } from '../../components/terminal/index.js';
import { useAppState } from '../../hooks/useAppState.js';

function useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible) {
  const [view, setView] = useState({ mode: 'list' });
  const [showImport, setShowImport] = useState(false);

  const handleEdit = (standardId) => setView({ mode: 'edit', standardId });
  const handleNewStandard = () => setView({ mode: 'new' });
  const handleEditorBack = () => { setView({ mode: 'list' }); refresh(); };
  const handleSaved = (savedId) => { if (savedId) addVisible(savedId); setView({ mode: 'list' }); refresh(); };
  const handleDeleteWithCleanup = async (id) => { removeVisible(id); await handleDelete(id); };

  return {
    view,
    showImport, setShowImport,
    handleEdit, handleNewStandard, handleEditorBack,
    handleSaved, handleDeleteWithCleanup,
  };
}

function StandardsListView({ grouped, loading, error, actions, customizedCounts }) {
  return (
    <>
      {error && <p className="inline-error inline-error--spaced">{error}</p>}
      {loading ? (
        <div className="standards-loading">Loading standards...</div>
      ) : (
        <StandardsTable grouped={grouped} actions={actions} customizedCounts={customizedCounts} />
      )}
    </>
  );
}

export default function StandardsPage() {
  const { grouped, loading, error, refresh, handleDelete, handleDuplicate } = useStandards();
  const { isVisible, toggle, add: addVisible, remove: removeVisible } = useVisibleStandards();
  const { selectedProject } = useAppState();
  const { counts: customizedCounts } = useStandardsOverrides(selectedProject);
  const {
    view,
    showImport,
    setShowImport,
    handleEdit,
    handleNewStandard,
    handleEditorBack,
    handleSaved,
    handleDeleteWithCleanup,
  } = useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible);

  if (view.mode === 'edit' || view.mode === 'new') {
    return <StandardEditor standardId={view.standardId} isNew={view.mode === 'new'} onBack={handleEditorBack} onSaved={handleSaved} />;
  }

  const activeCount = grouped
    ? Object.values(grouped).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0)
    : 0;

  return (
    <div className="standards-page standards-page--terminal">
      <div className="standards-page-header standards-page-header--terminal">
        <TermHeader
          name="standards"
          sub={`manage evaluation standards and quality criteria · ${activeCount} active`}
        />
        <div className="standards-page-header-actions">
          <button type="button" className="btn-secondary" onClick={() => setShowImport(true)}>Import</button>
          <button type="button" className="btn-primary" onClick={handleNewStandard}>+ New Standard</button>
        </div>
      </div>
      <StandardsListView grouped={grouped} loading={loading} error={error} actions={{ onEdit: handleEdit, onDelete: handleDeleteWithCleanup, onDuplicate: handleDuplicate, isVisible, onToggleVisibility: toggle }} customizedCounts={customizedCounts} />
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={() => { setShowImport(false); refresh(); }} />}
    </div>
  );
}
