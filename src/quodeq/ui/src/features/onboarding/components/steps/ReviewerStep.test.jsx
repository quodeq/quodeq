import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { withStableQueryApi } from '../../../../test-utils/withQueryClient.jsx';
import { invalidateDimensionCache } from '../../../evaluation/hooks/usePluginDimensions.js';
import ReviewerStep from './ReviewerStep.jsx';
import { pickSelectOption, waitForSelectOption } from '../../../../test-utils/selectOption.js';

const detection = vi.hoisted(() => ({ value: null }));
vi.mock('../../hooks/useProviderDetection.js', () => ({ useProviderDetection: () => detection.value }));

const CATALOG = [
  { id: 'sonnet', label: 'Sonnet', efforts: [], defaultEffort: '', isDefault: true, pinned: false },
  { id: 'opus', label: 'Opus', efforts: [], defaultEffort: '', isDefault: false, pinned: false },
];
const FOLDER_ADD = { projectId: 'p1', cloning: false, name: 'billing', fileCount: 42, languages: ['python', 'typescript'] };
const CLONE_ADD = { projectId: null, cloning: true, name: 'billing', fileCount: null, languages: [] };

function makeApi() {
  return {
    getClientModels: vi.fn().mockResolvedValue({ catalog: CATALOG }),
    getOllamaModels: vi.fn().mockResolvedValue([]),
    getOllamaStatus: vi.fn().mockResolvedValue({ status: 'online' }),
    listPlugins: vi.fn().mockResolvedValue([{ dimensions: [{ id: 'security' }, { id: 'maintainability' }] }]),
    listStandards: vi.fn().mockResolvedValue([]),
  };
}

function renderStep(added = FOLDER_ADD, api = makeApi()) {
  const props = { added, onStart: vi.fn(), onLater: vi.fn(), onOpenSettings: vi.fn() };
  const Wrapper = withStableQueryApi(api);
  render(<Wrapper><ReviewerStep {...props} /></Wrapper>);
  return props;
}

const detected = (ids) => ({ status: 'detected', results: ids.map((id) => ({ id, detected: true })) });

describe('ReviewerStep', () => {
  beforeEach(() => {
    invalidateDimensionCache();
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['security', 'maintainability']));
  });
  afterEach(() => localStorage.clear());

  it('names the added project, its files and languages, with the first-run scope', async () => {
    detection.value = detected(['claude-code']);
    renderStep();
    expect(screen.getByText('✓ billing added · 42 source files · python · typescript')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Who reviews it' })).toBeInTheDocument();
    expect(await screen.findByText('all 2 dimensions · no time limit. you can change both on Evaluate.')).toBeInTheDocument();
  });

  it('start is disabled until a model is chosen', async () => {
    detection.value = detected(['ollama']);
    renderStep();
    await screen.findByText('all 2 dimensions · no time limit. you can change both on Evaluate.');
    expect(screen.getByRole('button', { name: 'start first evaluation' })).toBeDisabled();
  });

  it('start saves the reviewer and hands over the chosen model and every dimension', async () => {
    detection.value = detected(['claude-code']);
    const { onStart } = renderStep();
    const start = screen.getByRole('button', { name: 'start first evaluation' });
    await waitFor(() => expect(start).toBeEnabled());
    await screen.findByText('all 2 dimensions · no time limit. you can change both on Evaluate.');
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalledWith({ provider: { id: 'claude', model: 'sonnet' }, standardIds: ['security', 'maintainability'] });
    expect(localStorage.getItem('cc-active-provider')).toBe('claude');
  });

  it('clone add shows save and close and never launches', async () => {
    detection.value = detected(['claude-code']);
    const { onStart, onLater } = renderStep(CLONE_ADD);
    expect(screen.getByText('✓ billing added')).toBeInTheDocument();
    expect(screen.getByText('the download continues on Repositories. your reviewer is saved for its first evaluation.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'start first evaluation' })).toBeNull();
    await waitForSelectOption('Sonnet (default)');
    fireEvent.click(screen.getByRole('button', { name: 'save and close' }));
    expect(onLater).toHaveBeenCalledTimes(1);
    expect(onStart).not.toHaveBeenCalled();
    expect(localStorage.getItem('cc-claude-model')).toBe('sonnet');
  });

  it('later with no model picked writes nothing', () => {
    detection.value = detected(['ollama']);
    const { onLater } = renderStep();
    fireEvent.click(screen.getByRole('button', { name: 'later, take me to the project' }));
    expect(onLater).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('cc-active-provider')).toBeNull();
  });

  it('none detected offers settings instead of a list', () => {
    detection.value = { status: 'none', results: [] };
    const { onOpenSettings } = renderStep();
    expect(screen.getByText('no provider found on this machine.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'set one up in settings' }));
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'start first evaluation' })).toBeDisabled();
  });

  it('shows a quiet line while detection runs', () => {
    detection.value = { status: 'detecting', results: [] };
    renderStep();
    expect(screen.getByText('looking for models on this machine…')).toBeInTheDocument();
  });

  it('later for a returning user without changes leaves the stored reviewer untouched', async () => {
    localStorage.setItem('cc-active-provider', 'codex');
    detection.value = detected(['claude-code', 'codex-cli']);
    const { onLater } = renderStep();
    await waitForSelectOption('Sonnet (default)');
    expect(screen.getByRole('radio', { name: 'Codex CLI' })).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'later, take me to the project' }));
    expect(onLater).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('cc-active-provider')).toBe('codex');
    expect(localStorage.getItem('cc-codex-model')).toBeNull();
  });

  it('later after picking a model saves it', async () => {
    localStorage.setItem('cc-active-provider', 'codex');
    detection.value = detected(['claude-code', 'codex-cli']);
    renderStep();
    await waitForSelectOption('Sonnet (default)');
    pickSelectOption(screen.getByRole('combobox'), 'Opus');
    fireEvent.click(screen.getByRole('button', { name: 'later, take me to the project' }));
    expect(localStorage.getItem('cc-active-provider')).toBe('codex');
    expect(localStorage.getItem('cc-codex-model')).toBe('opus');
  });

  it('one scanned file reads in the singular', () => {
    detection.value = detected(['claude-code']);
    renderStep({ ...FOLDER_ADD, fileCount: 1, languages: ['python'] });
    expect(screen.getByText('✓ billing added · 1 source file · python')).toBeInTheDocument();
  });

  it('one file without languages reads in the singular', () => {
    detection.value = detected(['claude-code']);
    renderStep({ ...FOLDER_ADD, fileCount: 1, languages: [] });
    expect(screen.getByText('✓ billing added · 1 source file')).toBeInTheDocument();
  });

  it('a dimension load failure says why start stays disabled', async () => {
    detection.value = detected(['claude-code']);
    // Each list degrades to empty on its own; a malformed plugin list is
    // what makes the dimension load itself fail.
    const api = { ...makeApi(), listPlugins: vi.fn().mockResolvedValue([{ dimensions: null }]) };
    renderStep(FOLDER_ADD, api);
    expect(await screen.findByText(/Failed to load dimensions/)).toHaveAttribute('role', 'alert');
    expect(screen.getByRole('button', { name: 'start first evaluation' })).toBeDisabled();
  });

  it('a resumed project that already has runs starts an evaluation, not a first one', async () => {
    detection.value = detected(['claude-code']);
    const { onStart } = renderStep({ ...FOLDER_ADD, hasRuns: true });
    expect(screen.queryByRole('button', { name: 'start first evaluation' })).toBeNull();
    const start = screen.getByRole('button', { name: 'start evaluation' });
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalledWith({ provider: { id: 'claude', model: 'sonnet' }, standardIds: ['security', 'maintainability'] });
  });

  it('later with a stored provider that was not detected leaves storage untouched', async () => {
    localStorage.setItem('cc-active-provider', 'gemini');
    detection.value = detected(['claude-code', 'codex-cli']);
    const { onLater } = renderStep();
    await waitForSelectOption('Sonnet (default)');
    fireEvent.click(screen.getByRole('button', { name: 'later, take me to the project' }));
    expect(onLater).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('cc-active-provider')).toBe('gemini');
    expect(localStorage.getItem('cc-claude-model')).toBeNull();
  });

  it('later after selecting another provider row saves it', async () => {
    localStorage.setItem('cc-active-provider', 'codex');
    detection.value = detected(['claude-code', 'codex-cli']);
    renderStep();
    await waitForSelectOption('Sonnet (default)');
    fireEvent.click(screen.getByRole('radio', { name: 'Claude Code' }));
    fireEvent.click(screen.getByRole('button', { name: 'later, take me to the project' }));
    expect(localStorage.getItem('cc-active-provider')).toBe('claude');
  });
});
