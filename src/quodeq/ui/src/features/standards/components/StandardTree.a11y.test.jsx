import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import StandardTree from './StandardTree.jsx';

const STANDARD = {
  name: 'ISO 25010',
  principles: [
    { name: 'Maintainability', requirements: [{ id: 'M-1', text: 'Keep files short' }] },
  ],
};

// #6478 - the icon-only add/remove buttons in TreeNodeActions rely solely on
// `title`, which many screen readers don't reliably expose as a name; give
// them the same text via aria-label (title alone already satisfies the
// accessible-name computation dom-accessibility-api implements, so this
// asserts the attribute directly rather than via getByRole name matching).
describe('StandardTree icon-only action buttons a11y', () => {
  it('gives the root add-principle button an aria-label matching its title', () => {
    render(
      <StandardTree
        standard={STANDARD}
        selectedNode={{ type: 'root' }}
        actions={{ onSelectNode: vi.fn(), onAddPrinciple: vi.fn(), editable: true }}
      />,
    );
    const btn = screen.getByTitle('Add Principle');
    expect(btn).toHaveAttribute('aria-label', 'Add Principle');
  });

  it('gives the principle remove/add-requirement buttons an aria-label matching their title', () => {
    render(
      <StandardTree
        standard={STANDARD}
        selectedNode={{ type: 'root' }}
        actions={{
          onSelectNode: vi.fn(),
          onAddPrinciple: vi.fn(),
          onAddRequirement: vi.fn(),
          onRemovePrinciple: vi.fn(),
          onRemoveRequirement: vi.fn(),
          editable: true,
        }}
      />,
    );
    expect(screen.getByTitle('Remove Principle')).toHaveAttribute('aria-label', 'Remove Principle');
    expect(screen.getByTitle('Add Requirement')).toHaveAttribute('aria-label', 'Add Requirement');
  });
});
