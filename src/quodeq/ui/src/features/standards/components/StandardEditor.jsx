import { useState, useCallback, useRef, useEffect } from 'react';
import { useStandardDetail } from '../hooks/useStandardDetail.js';
import StandardTree from './StandardTree.jsx';
import StandardDetail from './StandardDetail.jsx';

const TYPE_LABELS = { builtin: 'ISO-25010', quodeq: 'Quodeq', community: 'Community', custom: 'Custom' };

const MIN_TREE_WIDTH = 180;
const MAX_TREE_WIDTH = 600;
const DEFAULT_TREE_WIDTH = 280;

function useResizable(defaultWidth) {
  const [width, setWidth] = useState(defaultWidth);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const onMouseDown = useCallback((e) => {
    e.preventDefault();
    dragging.current = true;
    startX.current = e.clientX;
    startWidth.current = width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [width]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!dragging.current) return;
      const delta = e.clientX - startX.current;
      const newWidth = Math.min(MAX_TREE_WIDTH, Math.max(MIN_TREE_WIDTH, startWidth.current + delta));
      setWidth(newWidth);
    };
    const onMouseUp = () => {
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  return { width, onMouseDown };
}

export default function StandardEditor({ standardId, isNew, onBack, onSaved }) {
  const {
    standard, loading, error, dirty, editable,
    selectedNode, setSelectedNode,
    updateField, addPrinciple, removePrinciple, addRequirement, removeRequirement,
    save,
  } = useStandardDetail(standardId, isNew);

  const { width: treeWidth, onMouseDown: onDividerMouseDown } = useResizable(DEFAULT_TREE_WIDTH);

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
        <div className="editor-toolbar-top">
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
        <div className="editor-toolbar-stats">
          <span className="editor-stat"><strong>{standard?.principles?.length || 0}</strong> principles</span>
          <span className="editor-stat-dot" />
          <span className="editor-stat"><strong>{(standard?.principles || []).reduce((sum, p) => sum + (p.requirements?.length || 0), 0)}</strong> requirements</span>
          <span className="editor-stat-dot" />
          <span className={`editor-stat-type editor-stat-type--${standard?.type || 'custom'}`}>
            {TYPE_LABELS[standard?.type] || 'Custom'}
          </span>
        </div>
      </div>

      {error && <p className="inline-error" style={{ margin: '8px 16px' }}>{error}</p>}

      <div className="standard-editor-body">
        <div className="standard-editor-tree-panel" style={{ width: treeWidth, minWidth: MIN_TREE_WIDTH, maxWidth: MAX_TREE_WIDTH }}>
          <StandardTree
            standard={standard}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            actions={{ onAddPrinciple: addPrinciple, onRemovePrinciple: removePrinciple, onAddRequirement: addRequirement, onRemoveRequirement: removeRequirement }}
            editable={editable}
          />
        </div>

        <div className="standard-editor-divider" onMouseDown={onDividerMouseDown} />

        <div className="standard-editor-detail-panel">
          <StandardDetail
            standard={standard}
            selectedNode={selectedNode}
            onUpdateField={updateField}
            editable={editable}
            isNew={isNew}
          />
        </div>
      </div>
    </div>
  );
}
