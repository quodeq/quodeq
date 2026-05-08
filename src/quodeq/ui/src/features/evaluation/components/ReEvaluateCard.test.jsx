import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { buildScanPayload, default as ReEvaluateCard } from './ReEvaluateCard.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneContext } from '../../side-pane/SidePaneContext.jsx';
import { invalidateDimensionCache } from '../hooks/usePluginDimensions.js';

const baseState = {
  info: { path: '/repos/myproject' },
  branch: null,
  scopePath: null,
  selectedDims: new Set(['security', 'maintainability']),
  cleanScan: 'off',
};

describe('buildScanPayload', () => {
  it('sets cleanScan: false and omits incremental when toggle is "off" (default)', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'off' });
    expect(payload.cleanScan).toBe(false);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "once"', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'once' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('sets cleanScan: true when toggle is "permanent"', () => {
    const payload = buildScanPayload({ ...baseState, cleanScan: 'permanent' });
    expect(payload.cleanScan).toBe(true);
    expect(payload).not.toHaveProperty('incremental');
  });

  it('includes repo path from info', () => {
    const payload = buildScanPayload({ ...baseState });
    expect(payload.repo).toBe('/repos/myproject');
  });

  it('includes selected dimensions as an array', () => {
    const payload = buildScanPayload({ ...baseState });
    expect(payload.dimensions).toEqual(['security', 'maintainability']);
  });

  it('includes branch when provided', () => {
    const payload = buildScanPayload({ ...baseState, branch: 'feat/my-branch' });
    expect(payload.branch).toBe('feat/my-branch');
  });

  it('omits branch when null', () => {
    const payload = buildScanPayload({ ...baseState, branch: null });
    expect(payload).not.toHaveProperty('branch');
  });

  it('includes scopePath when provided', () => {
    const payload = buildScanPayload({ ...baseState, scopePath: 'src/api' });
    expect(payload.scopePath).toBe('src/api');
  });

  it('omits scopePath when null', () => {
    const payload = buildScanPayload({ ...baseState, scopePath: null });
    expect(payload).not.toHaveProperty('scopePath');
  });
});

function makeFakeApi(overrides = {}) {
  return {
    getProjectInfo: vi.fn().mockResolvedValue(null),
    relocateProject: vi.fn().mockResolvedValue(null),
    cloneToLocal: vi.fn().mockResolvedValue(null),
    listPlugins: vi.fn().mockResolvedValue([]),
    listStandards: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

const stubSidePane = {
  showToast: vi.fn(),
  openWindow: vi.fn(),
  closeWindow: vi.fn(),
  registerWindowSpec: vi.fn(),
};

function renderCard({ project, projectInfo, api, onStart = vi.fn(), disabled = false } = {}) {
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
          />
        </SidePaneContext.Provider>
      </ApiProvider>
    </QueryWrapper>,
  );
}

describe('ReEvaluateCard ephemeral gating', () => {
  beforeEach(() => {
    invalidateDimensionCache();
  });

  it('disables re-evaluation when projectInfo.evaluable is false (ephemeral completed)', async () => {
    const projectInfo = {
      name: 'demo',
      path: '/tmp/cloned/repo',
      location: 'local',
      ephemeral: true,
      evaluable: false,
    };
    const api = makeFakeApi({ getProjectInfo: vi.fn().mockResolvedValue(projectInfo) });
    renderCard({ project: 'uuid-1', projectInfo, api });

    // The explanatory note appears
    await waitFor(() => {
      expect(
        screen.getByText(/ephemeral|working copy was deleted|one-shot/i),
      ).toBeInTheDocument();
    });

    // The scan button should be disabled
    const button = screen.getByRole('button', { name: /^▸\s*scan$|^scan$|running\.\.\./i });
    expect(button).toBeDisabled();
  });

  it('keeps re-evaluation enabled for normal local projects', async () => {
    const projectInfo = {
      name: 'demo',
      path: '/repos/myproj',
      location: 'local',
      ephemeral: false,
      evaluable: true,
    };
    const api = makeFakeApi({
      getProjectInfo: vi.fn().mockResolvedValue(projectInfo),
      listStandards: vi.fn().mockResolvedValue([]),
    });
    renderCard({ project: 'uuid-2', projectInfo, api });

    // Wait for info to render (path appears in the panel)
    await waitFor(() => {
      expect(screen.getByText('/repos/myproj')).toBeInTheDocument();
    });

    // No ephemeral note
    expect(
      screen.queryByText(/working copy was deleted|one-shot/i),
    ).not.toBeInTheDocument();

    // Scan button is not disabled
    const button = screen.getByRole('button', { name: /^▸\s*scan$|^scan$|running\.\.\./i });
    expect(button).not.toBeDisabled();
  });
});
