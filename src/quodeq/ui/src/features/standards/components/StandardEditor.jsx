import { useStandardDetail } from '../hooks/useStandardDetail.js';
import StandardTree from './StandardTree.jsx';
import StandardDetail from './StandardDetail.jsx';

export default function StandardEditor({ standardId, isNew, onBack, onSaved }) {
  const {
    standard, loading, error, dirty, editable,
    selectedNode, setSelectedNode,
    updateField, addPrinciple, removePrinciple, addRequirement, removeRequirement,
    save,
  } = useStandardDetail(standardId, isNew);

  const handleSave = async () => {
    await save();
    if (onSaved) onSaved(standard?.id);
  };

  if (loading) {
    return <div className="standard-editor-loading">Loading standard...</div>;
  }

  if (error) {
    return (
      <div className="standard-editor-error">
        <p className="inline-error">{error}</p>
        <button type="button" className="btn-secondary" onClick={onBack}>Back</button>
      </div>
    );
  }

  return (
    <div className="standard-editor">
      <div className="standard-editor-toolbar">
        <button type="button" className="editor-back-btn" onClick={onBack}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M19 12H5M12 5l-7 7 7 7" />
          </svg>
          Back
        </button>

        <div className="editor-toolbar-center">
          <h2 className="editor-title">
            {isNew ? 'New Standard' : (standard?.name || standardId)}
            {dirty && <span className="editor-dirty-indicator" title="Unsaved changes">*</span>}
          </h2>
          {standard?.managed && (
            <span className="editor-managed-badge">managed</span>
          )}
        </div>

        <div className="editor-toolbar-actions">
          {editable && (
            <button
              type="button"
              className="btn-primary"
              onClick={handleSave}
              disabled={!dirty}
            >
              Save
            </button>
          )}
        </div>
      </div>

      {error && <p className="inline-error" style={{ margin: '8px 16px' }}>{error}</p>}

      <div className="standard-editor-body">
        <div className="standard-editor-tree-panel">
          <StandardTree
            standard={standard}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            onAddPrinciple={addPrinciple}
            onRemovePrinciple={removePrinciple}
            onAddRequirement={addRequirement}
            onRemoveRequirement={removeRequirement}
            editable={editable}
          />
        </div>

        <div className="standard-editor-detail-panel">
          <StandardDetail
            standard={standard}
            selectedNode={selectedNode}
            onUpdateField={updateField}
            editable={editable}
          />
        </div>
      </div>
    </div>
  );
}
