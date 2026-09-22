import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import ReferenceEditor from './ReferenceEditor.jsx';

const fakeApi = { listCwes: vi.fn().mockResolvedValue([{ id: 79, name: 'XSS', abstraction: 'Base' }]) };

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

// #6417 - the CWE search input relies only on a placeholder, no accessible
// name.
// #6418 - the browser modal's close button has no accessible name beyond
// the bare "x" glyph.
describe('ReferenceEditor / CweBrowserModal a11y', () => {
  const openBrowser = async () => {
    const Wrapper = makeWrapper();
    const refs = [{ type: 'cwe', refId: '', name: '', url: '' }];
    render(
      <Wrapper>
        <ReferenceEditor refs={refs} onChange={vi.fn()} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByText('Select CWE...'));
    await waitFor(() => expect(fakeApi.listCwes).toHaveBeenCalled());
  };

  it('gives the CWE search input an accessible name', async () => {
    await openBrowser();
    expect(screen.getByRole('textbox', { name: 'Search CWE' })).toBeInTheDocument();
  });

  it('gives the modal close button an accessible name', async () => {
    await openBrowser();
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeInTheDocument();
  });
});
