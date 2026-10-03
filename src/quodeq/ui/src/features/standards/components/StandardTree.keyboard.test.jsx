import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import StandardTree from './StandardTree.jsx';

const STANDARD = {
  name: 'ISO 25010',
  principles: [
    { name: 'Maintainability', requirements: [{ id: 'M-1', text: 'Keep files short' }] },
  ],
};

function renderTree() {
  const actions = {
    onSelectNode: vi.fn(),
    onAddPrinciple: vi.fn(),
    onAddRequirement: vi.fn(),
    onRemovePrinciple: vi.fn(),
    onRemoveRequirement: vi.fn(),
    editable: true,
  };
  render(<StandardTree standard={STANDARD} selectedNode={{ type: 'root' }} actions={actions} />);
  return actions;
}

describe('StandardTree row keyboard handling', () => {
  it('selects the node on Enter on the row itself', () => {
    const actions = renderTree();
    const row = screen.getByTitle('Add Principle').closest('.tree-node-row');
    const notPrevented = fireEvent.keyDown(row, { key: 'Enter' });
    expect(actions.onSelectNode).toHaveBeenCalledWith({ type: 'root' });
    expect(notPrevented).toBe(false);
  });

  it.each(['Add Principle', 'Add Requirement', 'Remove Principle'])(
    'leaves Enter on the nested %s button to the button',
    (title) => {
      const actions = renderTree();
      const notPrevented = fireEvent.keyDown(screen.getByTitle(title), { key: 'Enter' });
      expect(actions.onSelectNode).not.toHaveBeenCalled();
      expect(notPrevented).toBe(true);
    },
  );
});
