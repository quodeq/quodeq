import { vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import ReEvaluateCard from './ReEvaluateCard.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneContext } from '../../side-pane/SidePaneContext.jsx';

/**
 * Shared render helpers for ReEvaluateCard.*.test.jsx siblings.
 *
 * Split out of ReEvaluateCard.test.jsx.
 */

export function makeFakeApi(overrides = {}) {
  return {
    getProjectInfo: vi.fn().mockResolvedValue(null),
    relocateProject: vi.fn().mockResolvedValue(null),
    listPlugins: vi.fn().mockResolvedValue([]),
    listStandards: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

export const stubSidePane = {
  showToast: vi.fn(),
  openWindow: vi.fn(),
  closeWindow: vi.fn(),
  registerWindowSpec: vi.fn(),
};

export function renderCard({ project, projectInfo, api, onStart = vi.fn(), disabled = false, preselectDims = [] } = {}) {
  const QueryWrapper = withQueryClient();
  return render(
    <QueryWrapper>
      <ApiProvider value={api}>
        <SidePaneContext.Provider value={stubSidePane}>
          <ReEvaluateCard
            project={project}
            projectInfo={projectInfo}
            onStart={onStart}
            disabled={disabled}
            preselectDims={preselectDims}
          />
        </SidePaneContext.Provider>
      </ApiProvider>
    </QueryWrapper>,
  );
}
