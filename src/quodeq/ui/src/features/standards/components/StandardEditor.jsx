import { useState, useCallback, useRef, useEffect } from 'react';
import { useStandardDetail } from '../hooks/useStandardDetail.js';
import StandardTree from './StandardTree.jsx';
import StandardDetail from './StandardDetail.jsx';
import { STANDARD_TYPES } from '../hooks/useStandards.js';
import { TermHeader } from '../../../components/terminal/index.js';

const TYPE_LABELS = { [STANDARD_TYPES.BUILTIN]: 'iso-25010', [STANDARD_TYPES.QUODEQ]: 'quodeq', [STANDARD_TYPES.COMMUNITY]: 'community', [STANDARD_TYPES.CUSTOM]: 'custom' };

const MIN_TREE_WIDTH = 180;
const MAX_TREE_WIDTH = 600;
const INLINE_ERROR_MARGIN = '8px 16px';
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

function buildSubLine({ standard, dirty }) {
  const principles = standard?.principles?.length || 0;
  const requirements = (standard?.principles || []).reduce((sum, p) => sum + (p.requirements?.length || 0), 0);
  const type = TYPE_LABELS[standard?.type] || 'custom';
  const dirtyMark = dirty ? ' · unsaved' : '';
  return `${principles} principle${principles === 1 ? '' : 's'} · ${requirements} requirement${requirements === 1 ? '' : 's'} · ${type}${dirtyMark}`;
}

function EditorToolbar({ meta, dirty, editable, onBack, onSave }) {
  const { isNew, standard, standardId } = meta;
  const title = isNew ? 'new standard' : (standard?.name || standardId || 'standard').toLowerCase();
  const sub = buildSubLine({ standard, dirty });
  return (
    <div className="standard-editor-toolbar">
      <TermHeader name={title} sub={sub} />
      <div className="standard-editor-actions">
        <button type="button" className="settings-pill" onClick={onBack}>← back</button>
        {editable && (
          <button
            type="button"
            className={`settings-pill${dirty ? ' settings-pill--active' : ''}`}
            onClick={onSave}
            disabled={!dirty}
          >save</button>
        )}
      </div>
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
      <div className="standard-editor-divider" role="separator" tabIndex={0} onMouseDown={onDividerMouseDown} onKeyDown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.preventDefault(); }} />
      <div className="standard-editor-detail-panel">
        <StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={updateField} editable={editable} isNew={isNew} />
      </div>
    </div>
  );
}

function EditorLoadingOrError({ loading, error, standard, onBack }) {
  if (loading) return <div className="standard-editor-loading">Loading standard…</div>;
  if (error && !standard) {
    return (
      <div className="standard-editor-error">
        <p className="inline-error">{error}</p>
        <button type="button" className="settings-pill" onClick={onBack}>← back</button>
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
    <div className="standard-editor standard-editor--terminal">
      <EditorToolbar
        meta={{ isNew, standard, standardId }}
        dirty={dirty} editable={editable}
        onBack={onBack} onSave={handleSave}
      />
      {error && <p className="inline-error" style={{ margin: INLINE_ERROR_MARGIN }}>{error}</p>}
      <EditorBody
        treeProps={{ standard, selectedNode, actions: treeActions, editable }}
        detailProps={{ updateField, isNew }}
        treeWidth={treeWidth}
        onDividerMouseDown={onDividerMouseDown}
      />
    </div>
  );
}
