import { useState } from 'react';
import { useStandards } from './hooks/useStandards.js';
import { useVisibleStandards } from './hooks/useVisibleStandards.js';
import { useStandardsOverrides } from './hooks/useStandardsOverrides.js';
import StandardsTable from './components/StandardsTable.jsx';
import StandardEditor from './components/StandardEditor.jsx';
import ImportModal from './components/ImportModal.jsx';
import { TermHeader } from '../../components/terminal/index.js';
import { useAppState } from '../../hooks/useAppState.js';
import { t } from '../../strings/index.js';

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
        <div className="standards-loading">{t('standards.loadingStandards')}</div>
      ) : (
        <StandardsTable grouped={grouped} actions={actions} customizedCounts={customizedCounts} />
      )}
    </>
  );
}

export default function StandardsPage({ onRescan }) {
  const { grouped, loading, error, refresh, handleDelete, handleDuplicate } = useStandards();
  const { selectedProject, selectedSource } = useAppState();
  // A shared (read-only) project has no local standards file to write; the
  // per-project PUT would 404 and vanish in persist()'s fire-and-forget
  // catch. The toggle still lands in the browser-local visible set, which
  // is what every screen filters by.
  const visibilityProjectId = selectedSource === 'shared' ? null : selectedProject;
  const { isVisible, toggle, add: addVisible, remove: removeVisible } = useVisibleStandards({ projectId: visibilityProjectId });
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
    return <StandardEditor standardId={view.standardId} isNew={view.mode === 'new'} onBack={handleEditorBack} onSaved={handleSaved} onRescan={onRescan} />;
  }

  const activeCount = grouped
    ? Object.values(grouped).reduce((sum, arr) => sum + (Array.isArray(arr) ? arr.length : 0), 0)
    : 0;

  return (
    <div className="standards-page standards-page--terminal">
      <div className="standards-page-header standards-page-header--terminal">
        <TermHeader
          name={t('standards.termName')}
          sub={t('standards.termSub', { count: activeCount })}
        />
        <div className="standards-page-header-actions">
          <button type="button" className="btn-secondary" onClick={() => setShowImport(true)}>{t('standards.importBtn')}</button>
          <button type="button" className="btn-primary" onClick={handleNewStandard}>{t('standards.newStandardBtn')}</button>
        </div>
      </div>
      <StandardsListView grouped={grouped} loading={loading} error={error} actions={{ onEdit: handleEdit, onDelete: handleDeleteWithCleanup, onDuplicate: handleDuplicate, isVisible, onToggleVisibility: toggle }} customizedCounts={customizedCounts} />
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={() => { setShowImport(false); refresh(); }} />}
    </div>
  );
}
