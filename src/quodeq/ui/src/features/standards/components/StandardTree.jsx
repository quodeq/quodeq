import { useState, useEffect } from 'react';

function TreeNodeRow({ node, actions, titles, showExpand, expanded, setExpanded }) {
  const { label, isSelected } = node;
  const { onClick, onAdd, onRemove } = actions;
  const { addTitle, removeTitle } = titles || {};

  return (
    <div
      className={`tree-node-row${isSelected ? ' tree-node-row--selected' : ''}`}
      onClick={() => { onClick(); if (showExpand) setExpanded((v) => !v); }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      {showExpand ? (
        <span className="tree-expand-btn" aria-hidden="true">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"
            style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 150ms' }}>
            <path d="M3 2l4 3-4 3V2z" />
          </svg>
        </span>
      ) : (
        <span className="tree-expand-btn tree-expand-btn--invisible" />
      )}

      <span className="tree-node-label">{label}</span>

      <div className="tree-node-actions" onClick={(e) => e.stopPropagation()}>
        {onAdd && (
          <button type="button" className="tree-action-btn" onClick={onAdd} title={addTitle || 'Add'}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        )}
        {onRemove && (
          <button type="button" className="tree-action-btn tree-action-btn--remove" onClick={onRemove} title={removeTitle || 'Remove'}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M5 12h14" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

function TreeNode({ node, actions, titles, children }) {
  const { depth = 0, alwaysExpanded = false, defaultExpanded = true, isSelected } = node;
  const [expanded, setExpanded] = useState(alwaysExpanded || defaultExpanded);

  useEffect(() => {
    if (isSelected && !expanded) setExpanded(true);
  }, [isSelected, expanded]);
  const hasChildren = children && children.length > 0;
  const showExpand = hasChildren && !alwaysExpanded;

  return (
    <div className={`tree-node tree-node--depth-${depth}`}>
      <TreeNodeRow
        node={node} actions={actions} titles={titles}
        showExpand={showExpand} expanded={expanded} setExpanded={setExpanded}
      />
      {(alwaysExpanded || expanded) && hasChildren && (
        <div className="tree-node-children">
          {children}
        </div>
      )}
    </div>
  );
}

function RequirementNode({ req, ri, pi, selectedNode, actions }) {
  const { onSelectNode, onRemoveRequirement, editable } = actions;
  const isReqSelected = selectedNode?.type === 'requirement' && selectedNode.principleIndex === pi && selectedNode.reqIndex === ri;
  const hasContent = req.text || req.description || (req.refs && req.refs.length > 0);
  const handleRemoveReq = () => {
    if (hasContent) {
      if (!window.confirm(`Delete requirement "${req.text ? (req.text.length > 40 ? req.text.slice(0, 40) + '...' : req.text) : 'Untitled'}"?`)) return;
    }
    onRemoveRequirement(pi, ri);
  };
  return (
    <TreeNode
      key={ri}
      node={{ label: req.text || `Requirement ${ri + 1}`, isSelected: isReqSelected, depth: 2 }}
      actions={{ onClick: () => onSelectNode({ type: 'requirement', principleIndex: pi, reqIndex: ri }), onRemove: editable ? handleRemoveReq : undefined }}
      titles={{ removeTitle: 'Remove Requirement' }}
    />
  );
}

function PrincipleNode({ principle, pi, selectedNode, actions }) {
  const { onSelectNode, onAddRequirement, onRemovePrinciple, onRemoveRequirement, editable } = actions;
  const isPrincipleSelected = selectedNode?.type === 'principle' && selectedNode.index === pi;
  const reqCount = principle.requirements?.length || 0;
  const handleRemovePrinciple = () => {
    if (reqCount > 0) {
      if (!window.confirm(`Delete "${principle.name || 'Untitled'}" and its ${reqCount} requirement${reqCount !== 1 ? 's' : ''}? This cannot be undone.`)) return;
    }
    onRemovePrinciple(pi);
  };
  return (
    <TreeNode
      key={pi}
      node={{ label: principle.name || `Principle ${pi + 1}`, isSelected: isPrincipleSelected, depth: 1, defaultExpanded: false }}
      actions={{ onClick: () => onSelectNode({ type: 'principle', index: pi }), onAdd: editable ? () => onAddRequirement(pi) : undefined, onRemove: editable ? handleRemovePrinciple : undefined }}
      titles={{ addTitle: 'Add Requirement', removeTitle: 'Remove Principle' }}
    >
      {(principle.requirements || []).map((req, ri) => (
        <RequirementNode key={ri} req={req} ri={ri} pi={pi} selectedNode={selectedNode} actions={actions} />
      ))}
    </TreeNode>
  );
}

export default function StandardTree({ standard, selectedNode, onSelectNode, actions, editable }) {
  const { onAddPrinciple, onRemovePrinciple, onAddRequirement, onRemoveRequirement } = actions || {};
  if (!standard) return null;

  const treeActions = { onSelectNode, onAddRequirement, onRemovePrinciple, onRemoveRequirement, editable };

  return (
    <div className="standard-tree">
      <TreeNode
        node={{ label: standard.name || 'Standard', isSelected: selectedNode?.type === 'root', depth: 0, alwaysExpanded: true }}
        actions={{ onClick: () => onSelectNode({ type: 'root' }), onAdd: editable ? onAddPrinciple : undefined }}
        titles={{ addTitle: 'Add Principle' }}
      >
        {(standard.principles || []).map((principle, pi) => (
          <PrincipleNode key={pi} principle={principle} pi={pi} selectedNode={selectedNode} actions={treeActions} />
        ))}
      </TreeNode>
    </div>
  );
}
