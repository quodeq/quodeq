import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import { withStableQueryApi } from '../../../test-utils/withQueryClient.jsx';

// Catalog swap standing in for a language change: see
// DimensionSelector.i18n.test.jsx for why the mock is shaped this way.
const catalog = vi.hoisted(() => ({ current: {} }));

vi.mock('../../../strings/index.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    t: (key, vars) => (Object.hasOwn(catalog.current, key) ? catalog.current[key] : actual.t(key, vars)),
  };
});

// eslint-disable-next-line import/first -- must follow the vi.mock hoist above
import OmlxTab from './OmlxTab.jsx';

const fakeApi = {
  getOmlxModels: vi.fn().mockResolvedValue([]),
  testOmlxConcurrency: vi.fn(),
  getOmlxStatus: vi.fn().mockResolvedValue({ running: false }),
};

const Wrapper = withStableQueryApi(fakeApi);

function openModelHint(getByLabelText) {
  fireEvent.click(getByLabelText('Model help'));
}

describe('OmlxTab model hint', () => {
  afterEach(() => { catalog.current = {}; });

  it('re-resolves the hint text when the catalog changes', async () => {
    const state = { model: '', subagents: '4', 'time-limit-min': '60' };
    const { getByLabelText, getByRole, rerender } = render(
      <Wrapper><OmlxTab state={state} update={vi.fn()} /></Wrapper>,
    );
    openModelHint(getByLabelText);
    await waitFor(() => {
      expect(getByRole('tooltip').textContent).toContain('This list comes from your local omlx server');
    });

    catalog.current = { 'settings.omlxModelHint': 'Deze lijst komt van `omlx`.' };
    rerender(<Wrapper><OmlxTab state={{ ...state }} update={vi.fn()} /></Wrapper>);
    await waitFor(() => {
      expect(getByRole('tooltip').textContent).toBe('Deze lijst komt van omlx.');
    });
    expect(getByRole('tooltip').querySelector('code').textContent).toBe('omlx');
  });
});
