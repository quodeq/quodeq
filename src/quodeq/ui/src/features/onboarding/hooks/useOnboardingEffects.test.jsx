import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useOnboardingEffects } from './useOnboardingEffects.js';

vi.mock('../../../api/index.js', () => ({
  listStandards: vi.fn(async () => []),
  getProjectScan: vi.fn(),
}));

vi.mock('./useWizardDraft.js', () => ({
  saveDraft: vi.fn(),
}));

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import { getProjectScan, listStandards } from '../../../api/index.js';

function setup(overrides = {}) {
  const wizard = {
    state: {
      step: 'repo', repo: null, provider: null, providerView: null,
      standardIds: new Set(), totalTimeLimitS: null,
    },
    succeedScan: vi.fn(),
    seedStandards: vi.fn(),
  };
  const entry = { presetProjectId: 'proj-1' };
  const hook = renderHook(() => useOnboardingEffects({
    wizard, entry, setStandards: vi.fn(), ...overrides,
  }));
  return { ...hook, wizard };
}

describe('useOnboardingEffects', () => {
  it('logs a failed resume-scan fetch instead of swallowing it', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    getProjectScan.mockRejectedValueOnce(new Error('scan fetch failed'));

    setup();

    await waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('[useOnboardingEffects]'),
        expect.any(Error),
      );
    });
  });

  it('seeds the default standard: the default id when listed, else every visible standard', async () => {
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['security', 'performance', 'default']));
    getProjectScan.mockResolvedValue(null);
    listStandards.mockResolvedValueOnce([{ id: 'security' }, { id: 'performance' }, { id: 'hidden' }]);
    const first = setup();
    await waitFor(() => expect(first.wizard.seedStandards).toHaveBeenCalledWith(['security', 'performance']));

    listStandards.mockResolvedValueOnce([{ id: 'security' }, { id: 'default' }]);
    const second = setup();
    await waitFor(() => expect(second.wizard.seedStandards).toHaveBeenCalledWith(['default']));
    localStorage.clear();
  });

  it('logs a failed standards fetch instead of swallowing it', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    listStandards.mockRejectedValueOnce(new Error('standards fetch failed'));
    getProjectScan.mockResolvedValueOnce(null);
    const setStandards = vi.fn();

    setup({ setStandards });

    await waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('[useOnboardingEffects] standards fetch failed'),
        expect.any(Error),
      );
    });
    expect(setStandards).toHaveBeenCalledWith([]);
  });
});
