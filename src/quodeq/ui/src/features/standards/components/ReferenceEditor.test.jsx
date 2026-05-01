import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import ReferenceEditor from './ReferenceEditor.jsx';

const fakeApi = {
  listCwes: vi.fn(),
};

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

describe('ReferenceEditor / CweBrowserModal', () => {
  beforeEach(() => {
    fakeApi.listCwes.mockReset();
  });

  it('loads CWEs when the browser modal opens', async () => {
    fakeApi.listCwes.mockResolvedValue([
      { id: 79, name: 'XSS', abstraction: 'Base' },
      { id: 89, name: 'SQL Injection', abstraction: 'Base' },
    ]);
    const Wrapper = makeWrapper();
    const refs = [{ type: 'cwe', refId: '', name: '', url: '' }];
    const onChange = vi.fn();
    render(
      <Wrapper>
        <ReferenceEditor refs={refs} onChange={onChange} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByText('Select CWE...'));
    await waitFor(() => {
      expect(fakeApi.listCwes).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText('XSS')).toBeTruthy();
      expect(screen.getByText('SQL Injection')).toBeTruthy();
    });
  });

  it('shows the CWE error banner when listCwes rejects', async () => {
    fakeApi.listCwes.mockRejectedValue(new Error('cwe down'));
    const Wrapper = makeWrapper();
    const refs = [{ type: 'cwe', refId: '', name: '', url: '' }];
    const onChange = vi.fn();
    render(
      <Wrapper>
        <ReferenceEditor refs={refs} onChange={onChange} />
      </Wrapper>,
    );
    fireEvent.click(screen.getByText('Select CWE...'));
    await waitFor(() => {
      expect(screen.getByText(/Failed to load CWE list/i)).toBeTruthy();
    });
  });
});
