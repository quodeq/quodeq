import { useState, useEffect, useRef } from 'react';
import { resolveRequirementText } from '../resolveRequirementText.js';
import { t } from '../../../strings/index.js';

function TreeExpandIcon({ showExpand, expanded }) {
  if (!showExpand) return <span className="tree-expand-btn tree-expand-btn--invisible" />;
  return (
    <span className="tree-expand-btn" aria-hidden="true">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"
        style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 150ms' }}>
        <path d="M3 2l4 3-4 3V2z" />
      </svg>
    </span>
  );
}

function TreeNodeActions({ onAdd, onRemove, addTitle, removeTitle }) {
  return (
    <div className="tree-node-actions" onClick={(e) => e.stopPropagation()}>
      {onAdd && (
        <button type="button" className="tree-action-btn" onClick={onAdd} title={addTitle || t('standards.add')}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      )}
      {onRemove && (
        <button type="button" className="tree-action-btn tree-action-btn--remove" onClick={onRemove} title={removeTitle || t('standards.remove')}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="M5 12h14" />
          </svg>
        </button>
      )}
    </div>
  );
}

function TreeNodeRow({ node, actions, titles, expand }) {
  const { label, isSelected } = node;
  const { onClick, onAdd, onRemove } = actions;
  const { addTitle, removeTitle } = titles || {};
  const { showExpand, expanded, setExpanded } = expand || {};

  return (
    <div
      className={`tree-node-row${isSelected ? ' tree-node-row--selected' : ''}`}
      onClick={() => { onClick(); if (showExpand) setExpanded((v) => !v); }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
          if (showExpand) setExpanded((v) => !v);
        }
      }}
    >
      <TreeExpandIcon showExpand={showExpand} expanded={expanded} />

      <span className={`tree-node-label${node.customized ? ' tree-node-label--customized' : ''}`}>{label}</span>

      <TreeNodeActions onAdd={onAdd} onRemove={onRemove} addTitle={addTitle} removeTitle={removeTitle} />
    </div>
  );
}

function TreeNode({ node, actions, titles, children }) {
  const { depth = 0, alwaysExpanded = false, defaultExpanded = true, isSelected } = node;
  const [expanded, setExpanded] = useState(alwaysExpanded || defaultExpanded);
  const prevSelected = useRef(isSelected);

  useEffect(() => {
    // Auto-expand only when selection arrives from outside the tree (e.g. a
    // principle was just added programmatically). Re-firing on every render
    // while the row stays selected would block the user from collapsing the
    // currently-selected node by clicking it.
    if (isSelected && !prevSelected.current) setExpanded(true);
    prevSelected.current = isSelected;
  }, [isSelected]);
  const hasChildren = Array.isArray(children) ? children.length > 0 : !!children;
  const showExpand = hasChildren && !alwaysExpanded;

  return (
    <div className={`tree-node tree-node--depth-${depth}`}>
      <TreeNodeRow
        node={node} actions={actions} titles={titles}
        expand={{ showExpand, expanded, setExpanded }}
      />
      {(alwaysExpanded || expanded) && hasChildren && (
        <div className="tree-node-children">
          {children}
        </div>
      )}
    </div>
  );
}

const MAX_LABEL_DISPLAY_LENGTH = 40;

function RequirementNode({ req, position, selectedNode, actions, confirmFn = window.confirm, customizedIds, overrides }) {
  const { ri, pi } = position;
  const { onSelectNode, onRemoveRequirement, editable } = actions;
  const isReqSelected = selectedNode?.type === 'requirement' && selectedNode.principleIndex === pi && selectedNode.reqIndex === ri;
  const isCustomized = customizedIds.has(req.id);
  const hasContent = req.text || req.description || (req.refs && req.refs.length > 0);
  const resolvedText = resolveRequirementText(req, overrides?.[req.id]);
  const handleRemoveReq = () => {
    if (hasContent) {
      const label = resolvedText
        ? (resolvedText.length > MAX_LABEL_DISPLAY_LENGTH ? resolvedText.slice(0, MAX_LABEL_DISPLAY_LENGTH) + '...' : resolvedText)
        : t('standards.untitled');
      if (!confirmFn(t('standards.deleteReqConfirm', { label }))) return;
    }
    onRemoveRequirement(pi, ri);
  };
  return (
    <TreeNode
      key={ri}
      node={{ label: resolvedText || t('standards.requirementN', { n: ri + 1 }), isSelected: isReqSelected, depth: 2, customized: isCustomized }}
      actions={{ onClick: () => onSelectNode({ type: 'requirement', principleIndex: pi, reqIndex: ri }), onRemove: editable ? handleRemoveReq : undefined }}
      titles={{ removeTitle: t('standards.removeRequirement') }}
    />
  );
}

function PrincipleNode({ principle, pi, selectedNode, actions, confirmFn = window.confirm, customizedIds, overrides }) {
  const { onSelectNode, onAddRequirement, onRemovePrinciple, onRemoveRequirement, editable } = actions;
  const isPrincipleSelected = selectedNode?.type === 'principle' && selectedNode.index === pi;
  const reqCount = principle.requirements?.length || 0;
  const handleRemovePrinciple = () => {
    if (reqCount > 0) {
      const name = principle.name || t('standards.untitled');
      const message = reqCount === 1
        ? t('standards.deletePrincipleConfirmOne', { name, count: reqCount })
        : t('standards.deletePrincipleConfirmMany', { name, count: reqCount });
      if (!confirmFn(message)) return;
    }
    onRemovePrinciple(pi);
  };
  return (
    <TreeNode
      key={pi}
      node={{ label: principle.name || t('standards.principleN', { n: pi + 1 }), isSelected: isPrincipleSelected, depth: 1, defaultExpanded: false }}
      actions={{ onClick: () => onSelectNode({ type: 'principle', index: pi }), onAdd: editable ? () => onAddRequirement(pi) : undefined, onRemove: editable ? handleRemovePrinciple : undefined }}
      titles={{ addTitle: t('standards.addRequirement'), removeTitle: t('standards.removePrinciple') }}
    >
      {(principle.requirements || []).map((req, ri) => (
        <RequirementNode key={ri} req={req} position={{ ri, pi }} selectedNode={selectedNode} actions={actions} confirmFn={confirmFn} customizedIds={customizedIds} overrides={overrides} />
      ))}
    </TreeNode>
  );
}

function PrinciplesList({ principles, selectedNode, actions, confirmFn, customizedIds, overrides }) {
  return (principles || []).map((principle, pi) => (
    <PrincipleNode key={pi} principle={principle} pi={pi} selectedNode={selectedNode} actions={actions} confirmFn={confirmFn} customizedIds={customizedIds} overrides={overrides} />
  ));
}

export default function StandardTree({ standard, selectedNode, actions, confirmFn = window.confirm, overrides }) {
  const { onAddPrinciple, onRemovePrinciple, onAddRequirement, onRemoveRequirement, onSelectNode, editable } = actions || {};
  if (!standard) return null;

  const treeActions = { onSelectNode, onAddRequirement, onRemovePrinciple, onRemoveRequirement, editable };
  const customizedIds = new Set(overrides ? Object.keys(overrides) : []);

  return (
    <div className="standard-tree">
      <TreeNode
        node={{ label: standard.name || t('standards.standardLabel'), isSelected: selectedNode?.type === 'root', depth: 0, alwaysExpanded: true }}
        actions={{ onClick: () => onSelectNode({ type: 'root' }), onAdd: editable ? onAddPrinciple : undefined }}
        titles={{ addTitle: t('standards.addPrinciple') }}
      >
        <PrinciplesList principles={standard.principles} selectedNode={selectedNode} actions={treeActions} confirmFn={confirmFn} customizedIds={customizedIds} overrides={overrides} />
      </TreeNode>
    </div>
  );
}
