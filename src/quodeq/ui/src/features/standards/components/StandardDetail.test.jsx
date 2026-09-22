import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import StandardDetail from './StandardDetail.jsx';

describe('StandardDetail — indexing into a possibly-missing principles/requirements array', () => {
  it('does not throw when standard.principles is missing (principle node)', () => {
    const standard = { id: 's', name: 'S' }; // no principles array at all
    const selectedNode = { type: 'principle', index: 0 };
    expect(() =>
      render(<StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={vi.fn()} editable={true} isNew={false} />)
    ).not.toThrow();
  });

  it('renders nothing when standard.principles is missing (principle node)', () => {
    const standard = { id: 's', name: 'S' }; // no principles array at all
    const selectedNode = { type: 'principle', index: 0 };
    const { container } = render(
      <StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={vi.fn()} editable={true} isNew={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('does not throw when standard.principles is missing (requirement node)', () => {
    const standard = { id: 's', name: 'S' }; // no principles array at all
    const selectedNode = { type: 'requirement', principleIndex: 0, reqIndex: 0 };
    expect(() =>
      render(<StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={vi.fn()} editable={true} isNew={false} />)
    ).not.toThrow();
  });

  it('renders nothing when standard.principles is missing (requirement node)', () => {
    const standard = { id: 's', name: 'S' }; // no principles array at all
    const selectedNode = { type: 'requirement', principleIndex: 0, reqIndex: 0 };
    const { container } = render(
      <StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={vi.fn()} editable={true} isNew={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('does not throw when the principle exists but has no requirements array', () => {
    const standard = { id: 's', name: 'S', principles: [{ name: 'P', description: '' }] }; // no requirements
    const selectedNode = { type: 'requirement', principleIndex: 0, reqIndex: 0 };
    expect(() =>
      render(<StandardDetail standard={standard} selectedNode={selectedNode} onUpdateField={vi.fn()} editable={true} isNew={false} />)
    ).not.toThrow();
  });
});
