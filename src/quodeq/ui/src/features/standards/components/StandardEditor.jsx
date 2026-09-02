import { useState, useCallback, useRef, useEffect } from 'react';
import { useStandardDetail } from '../hooks/useStandardDetail.js';
import { useStandardEditorOverrides } from '../hooks/useStandardEditorOverrides.js';
import StandardTree from './StandardTree.jsx';
import StandardDetail from './StandardDetail.jsx';
import ThresholdImpactDialog from './ThresholdImpactDialog.jsx';
import { STANDARD_TYPES } from '../hooks/useStandards.js';
import { TermHeader } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

const TYPE_LABELS = { [STANDARD_TYPES.BUILTIN]: t('standards.baseIso'), [STANDARD_TYPES.QUODEQ]: t('standards.baseQuodeq'), [STANDARD_TYPES.COMMUNITY]: t('standards.baseCommunity'), [STANDARD_TYPES.CUSTOM]: t('standards.baseCustom') };

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
  const type = TYPE_LABELS[standard?.type] || t('standards.baseCustom');
  const dirtyMark = dirty ? ` · ${t('standards.unsaved')}` : '';
  const principlesPart = principles === 1 ? t('standards.principlesCountOne', { count: principles }) : t('standards.principlesCountMany', { count: principles });
  const requirementsPart = requirements === 1 ? t('standards.requirementsCountOne', { count: requirements }) : t('standards.requirementsCountMany', { count: requirements });
  return `${principlesPart} · ${requirementsPart} · ${type}${dirtyMark}`;
}

function EditorToolbar({ meta, dirty, editable, overridesDirty, customizedCount, onBack, onSave }) {
  const { isNew, standard, standardId } = meta;
  const title = isNew ? t('standards.newStandardTermName') : (standard?.name || standardId || t('standards.standardFallback')).toLowerCase();
  const sub = buildSubLine({ standard, dirty });
  const showSave = editable || overridesDirty;
  const saveDirty = dirty || overridesDirty;
  return (
    <div className="standard-editor-toolbar">
      <TermHeader name={title} sub={sub} />
      <div className="standard-editor-actions">
        {customizedCount > 0 && (
          <span className="standards-customized-badge">{t('standards.thresholdsCustomized', { count: customizedCount })}</span>
        )}
        <button type="button" className="settings-pill" onClick={onBack}>← {t('standards.back')}</button>
        {showSave && (
          <button
            type="button"
            className={`settings-pill${saveDirty ? ' settings-pill--active' : ''}`}
            onClick={onSave}
            disabled={!saveDirty}
          >{t('standards.saveBtn')}</button>
        )}
      </div>
    </div>
  );
}

function EditorBody({ treeProps, detailProps, treeWidth, onDividerMouseDown }) {
  const { standard, selectedNode, actions, editable, overrides } = treeProps;
  const { updateField, isNew, onChangeParam } = detailProps;
  return (
    <div className="standard-editor-body">
      <div className="standard-editor-tree-panel" style={{ width: treeWidth, minWidth: MIN_TREE_WIDTH, maxWidth: MAX_TREE_WIDTH }}>
        <StandardTree standard={standard} selectedNode={selectedNode} actions={actions} overrides={overrides} />
      </div>
      <div className="standard-editor-divider" role="separator" tabIndex={0} onMouseDown={onDividerMouseDown} onKeyDown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.preventDefault(); }} />
      <div className="standard-editor-detail-panel">
        <StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={updateField} editable={editable} isNew={isNew} overrides={overrides} onChangeParam={onChangeParam} />
      </div>
    </div>
  );
}

function EditorLoadingOrError({ loading, error, standard, onBack }) {
  if (loading) return <div className="standard-editor-loading">{t('standards.loadingStandard')}</div>;
  if (error && !standard) {
    return (
      <div className="standard-editor-error">
        <p className="inline-error">{error}</p>
        <button type="button" className="settings-pill" onClick={onBack}>← {t('standards.back')}</button>
      </div>
    );
  }
  return null;
}

function buildTreeActions({ addPrinciple, removePrinciple, addRequirement, removeRequirement, setSelectedNode, editable }) {
  return { onAddPrinciple: addPrinciple, onRemovePrinciple: removePrinciple, onAddRequirement: addRequirement, onRemoveRequirement: removeRequirement, onSelectNode: setSelectedNode, editable };
}

export default function StandardEditor({ standardId, isNew, onBack, onSaved, onRescan }) {
  const {
    standard, loading, error, dirty, editable,
    selectedNode, setSelectedNode,
    updateField, addPrinciple, removePrinciple, addRequirement, removeRequirement,
    save,
  } = useStandardDetail(standardId, isNew);

  const {
    selectedProject, overrides, overridesDirty, overridesSaveError, pendingImpact, setPendingImpact,
    customizedCount, handleChangeParam, commitSave, handleSave,
  } = useStandardEditorOverrides({ standard, editable, save, onSaved, onRescan });

  const { width: treeWidth, onMouseDown: onDividerMouseDown } = useResizable(DEFAULT_TREE_WIDTH);

  const earlyReturn = EditorLoadingOrError({ loading, error, standard, onBack });
  if (earlyReturn) return earlyReturn;

  const treeActions = buildTreeActions({ addPrinciple, removePrinciple, addRequirement, removeRequirement, setSelectedNode, editable });
  const onChangeParam = selectedProject ? handleChangeParam : undefined;

  return (
    <div className="standard-editor standard-editor--terminal">
      <EditorToolbar
        meta={{ isNew, standard, standardId }}
        dirty={dirty} editable={editable}
        overridesDirty={overridesDirty} customizedCount={customizedCount}
        onBack={onBack} onSave={handleSave}
      />
      {error && <p className="inline-error" style={{ margin: INLINE_ERROR_MARGIN }}>{error}</p>}
      {overridesSaveError && <p className="inline-error" style={{ margin: INLINE_ERROR_MARGIN }}>{overridesSaveError}</p>}
      <EditorBody
        treeProps={{ standard, selectedNode, actions: treeActions, editable, overrides }}
        detailProps={{ updateField, isNew, onChangeParam }}
        treeWidth={treeWidth}
        onDividerMouseDown={onDividerMouseDown}
      />
      {pendingImpact && (
        <ThresholdImpactDialog
          changedDimensions={pendingImpact}
          onCancel={() => setPendingImpact(null)}
          onSave={() => commitSave()}
          onSaveAndRescan={onRescan ? () => commitSave(pendingImpact) : undefined}
        />
      )}
    </div>
  );
}
