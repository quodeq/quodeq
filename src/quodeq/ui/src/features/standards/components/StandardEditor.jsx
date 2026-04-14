import { useState, useCallback, useRef, useEffect } from 'react';
import { useStandardDetail } from '../hooks/useStandardDetail.js';
import StandardTree from './StandardTree.jsx';
import StandardDetail from './StandardDetail.jsx';
import { STANDARD_TYPES } from '../hooks/useStandards.js';

const TYPE_LABELS = { [STANDARD_TYPES.BUILTIN]: 'ISO-25010', [STANDARD_TYPES.QUODEQ]: 'Quodeq', [STANDARD_TYPES.COMMUNITY]: 'Community', [STANDARD_TYPES.CUSTOM]: 'Custom' };

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
    if (typeof document !== 'undefined') {
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }
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
      if (typeof document !== 'undefined') {
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
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

function EditorToolbar({ meta, dirty, editable, onBack, onSave }) {
  const { isNew, standard, standardId } = meta;
  return (
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
          {editable && <button type="button" className="btn-primary" onClick={onSave} disabled={!dirty}>Save</button>}
        </div>
      </div>
      <EditorStatsRow standard={standard} />
    </div>
  );
}

function EditorStatsRow({ standard }) {
  return (
    <div className="editor-toolbar-stats">
      <span className="editor-stat"><strong>{standard?.principles?.length || 0}</strong> principles</span>
      <span className="editor-stat-dot" />
      <span className="editor-stat"><strong>{(standard?.principles || []).reduce((sum, p) => sum + (p.requirements?.length || 0), 0)}</strong> requirements</span>
      <span className="editor-stat-dot" />
      <span className={`editor-stat-type editor-stat-type--${standard?.type || STANDARD_TYPES.CUSTOM}`}>{TYPE_LABELS[standard?.type] || 'Custom'}</span>
    </div>
  );
}

function EditorBody({ treeProps, detailProps, treeWidth, onDividerMouseDown }) {
  const { standard, selectedNode, actions, editable } = treeProps;
  const { updateField, isNew } = detailProps;
  return (
    <div className="standard-editor-body">
      <div className="standard-editor-tree-panel" style={{ width: treeWidth, minWidth: MIN_TREE_WIDTH, maxWidth: MAX_TREE_WIDTH }}>
        <StandardTree standard={standard} selectedNode={selectedNode} actions={actions} />
      </div>
      <div className="standard-editor-divider" onMouseDown={onDividerMouseDown} />
      <div className="standard-editor-detail-panel">
        <StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={updateField} editable={editable} isNew={isNew} />
      </div>
    </div>
  );
}

function EditorLoadingOrError({ loading, error, standard, onBack }) {
  if (loading) return <div className="standard-editor-loading">Loading standard...</div>;
  if (error && !standard) {
    return (
      <div className="standard-editor-error">
        <p className="inline-error">{error}</p>
        <button type="button" className="btn-secondary" onClick={onBack}>Back</button>
      </div>
    );
  }
  return null;
}

function buildTreeActions({ addPrinciple, removePrinciple, addRequirement, removeRequirement, setSelectedNode, editable }) {
  return { onAddPrinciple: addPrinciple, onRemovePrinciple: removePrinciple, onAddRequirement: addRequirement, onRemoveRequirement: removeRequirement, onSelectNode: setSelectedNode, editable };
}

export default function StandardEditor({ standardId, isNew, onBack, onSaved }) {
  const {
    standard, loading, error, dirty, editable,
    selectedNode, setSelectedNode,
    updateField, addPrinciple, removePrinciple, addRequirement, removeRequirement,
    save,
  } = useStandardDetail(standardId, isNew);

  const { width: treeWidth, onMouseDown: onDividerMouseDown } = useResizable(DEFAULT_TREE_WIDTH);
  const handleSave = async () => { await save(); if (onSaved) onSaved(standard?.id); };

  const earlyReturn = EditorLoadingOrError({ loading, error, standard, onBack });
  if (earlyReturn) return earlyReturn;

  const treeActions = buildTreeActions({ addPrinciple, removePrinciple, addRequirement, removeRequirement, setSelectedNode, editable });

  return (
    <div className="standard-editor">
      <EditorToolbar
        meta={{ isNew, standard, standardId }}
        dirty={dirty} editable={editable}
        onBack={onBack} onSave={handleSave}
      />
      {error && <p className="inline-error" style={{ margin: '8px 16px' }}>{error}</p>}
      <EditorBody
        treeProps={{ standard, selectedNode, actions: treeActions, editable }}
        detailProps={{ updateField, isNew }}
        treeWidth={treeWidth}
        onDividerMouseDown={onDividerMouseDown}
      />
    </div>
  );
}
