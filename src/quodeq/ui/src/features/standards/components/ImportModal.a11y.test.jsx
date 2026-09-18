import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import ImportModal from './ImportModal.jsx';

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={{ importStandard: vi.fn() }}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

// #7410 - the file input has no programmatically associated label; give it
// an aria-label.
describe('ImportModal file input a11y', () => {
  it('gives the file input an accessible name', () => {
    const Wrapper = makeWrapper();
    render(
      <Wrapper>
        <ImportModal onClose={vi.fn()} onImported={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByLabelText('Standard file to import')).toHaveAttribute('type', 'file');
  });
});
