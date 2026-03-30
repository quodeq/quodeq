import { useState } from 'react';

function TreeNode({ label, isSelected, onClick, onAdd, onRemove, addTitle, removeTitle, children, depth = 0, alwaysExpanded = false, defaultExpanded = true }) {
  const [expanded, setExpanded] = useState(alwaysExpanded || defaultExpanded);
  const hasChildren = children && children.length > 0;
  const showExpand = hasChildren && !alwaysExpanded;

  return (
    <div className={`tree-node tree-node--depth-${depth}`}>
      <div
        className={`tree-node-row${isSelected ? ' tree-node-row--selected' : ''}`}
        onClick={onClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && onClick()}
      >
        {showExpand ? (
          <button
            type="button"
            className="tree-expand-btn"
            onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"
              style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 150ms' }}>
              <path d="M3 2l4 3-4 3V2z" />
            </svg>
          </button>
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

      {(alwaysExpanded || expanded) && hasChildren && (
        <div className="tree-node-children">
          {children}
        </div>
      )}
    </div>
  );
}

export default function StandardTree({ standard, selectedNode, onSelectNode, onAddPrinciple, onRemovePrinciple, onAddRequirement, onRemoveRequirement, editable }) {
  if (!standard) return null;

  const isRootSelected = selectedNode?.type === 'root';

  return (
    <div className="standard-tree">
      <TreeNode
        label={standard.name || 'Standard'}
        isSelected={isRootSelected}
        onClick={() => onSelectNode({ type: 'root' })}
        onAdd={editable ? onAddPrinciple : undefined}
        addTitle="Add Principle"
        depth={0}
        alwaysExpanded
      >
        {(standard.principles || []).map((principle, pi) => {
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
              label={principle.name || `Principle ${pi + 1}`}
              isSelected={isPrincipleSelected}
              onClick={() => onSelectNode({ type: 'principle', index: pi })}
              onAdd={editable ? () => onAddRequirement(pi) : undefined}
              onRemove={editable ? handleRemovePrinciple : undefined}
              addTitle="Add Requirement"
              removeTitle="Remove Principle"
              depth={1}
              defaultExpanded={false}
            >
              {(principle.requirements || []).map((req, ri) => {
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
                    label={req.text ? (req.text.length > 50 ? req.text.slice(0, 50) + '...' : req.text) : `Requirement ${ri + 1}`}
                    isSelected={isReqSelected}
                    onClick={() => onSelectNode({ type: 'requirement', principleIndex: pi, reqIndex: ri })}
                    onRemove={editable ? handleRemoveReq : undefined}
                    removeTitle="Remove Requirement"
                    depth={2}
                  />
                );
              })}
            </TreeNode>
          );
        })}
      </TreeNode>
    </div>
  );
}
