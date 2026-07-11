import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RequirementForm from './RequirementForm.jsx';

const REQ = {
  id: 'M-ANA-2',
  text: 'Functions MUST NOT exceed {max_lines} lines',
  description: 'Long functions are hard to reason about.',
  refs: [],
  params: { max_lines: { label: 'Max function lines', type: 'int', default: 50, min: 10, max: 500 } },
};

function renderForm(overrides = {}) {
  return render(
    <RequirementForm
      requirement={REQ}
      principleIndex={0}
      reqIndex={0}
      onUpdateField={() => {}}
      editable={false}
      reqOverrides={{}}
      onChangeParam={() => {}}
      {...overrides}
    />,
  );
}

describe('RequirementForm section order', () => {
  it('renders Thresholds after Description and before References', () => {
    renderForm();
    const description = screen.getByLabelText('Description');
    const thresholds = screen.getByText('Thresholds');
    const references = screen.getByText('References');

    // compareDocumentPosition: FOLLOWING (4) means the argument comes later
    // in document order than the node the method is called on.
    expect(
      description.compareDocumentPosition(thresholds) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      thresholds.compareDocumentPosition(references) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('omits the Thresholds section when the requirement declares no params', () => {
    renderForm({ requirement: { ...REQ, params: undefined } });
    expect(screen.queryByText('Thresholds')).not.toBeInTheDocument();
  });
});
