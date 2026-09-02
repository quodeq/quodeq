import { vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import SharedRepoSection from './SharedRepoSection.jsx';

/**
 * Shared fixtures for SharedRepoSection.*.test.jsx siblings.
 *
 * Split out of SharedRepoSection.test.jsx.
 */

export function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    disconnectShared: vi.fn(async () => ({ configured: false })),
    ...overrides,
  };
}

export function renderWithApi(fakeApi, props = {}) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ApiProvider value={fakeApi}><SharedRepoSection {...props} /></ApiProvider>
    </QC>
  );
}
