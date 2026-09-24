import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useHydratedCompliance } from './useHydratedCompliance.js';

const ref = { project: 'proj', asOf: null, dimension: 'security', generation: 1 };
const slim = (file, line) => ({
  file, line, endLine: null, principle: 'P1', title: 'ok',
  reason: null, snippet: null, context: null, detailDeferred: true, detailRef: ref,
});

function setup(getComplianceDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={client}>
      <ApiProvider value={{ getComplianceDetail }}>{children}</ApiProvider>
    </QueryClientProvider>
  );
  return wrapper;
}

describe('useHydratedCompliance', () => {
  it('fills deferred items with the fetched detail', async () => {
    const get = vi.fn(async () => [{ ...slim('src/a.py', 1), reason: 'why', snippet: 'code', context: 'ctx', detailDeferred: false }]);
    const items = [slim('src/a.py', 1)];
    const { result } = renderHook(() => useHydratedCompliance(items), { wrapper: setup(get) });

    expect(result.current[0].snippet).toBeNull();
    await waitFor(() => expect(result.current[0].snippet).toBe('code'));
    expect(result.current[0].reason).toBe('why');
    expect(result.current[0].context).toBe('ctx');
    expect(get).toHaveBeenCalledWith('proj', { dimension: 'security', asOf: null, principle: 'P1', pathPrefix: 'src/a.py' });
  });

  it('does not fetch when nothing is deferred', () => {
    const get = vi.fn();
    const items = [{ file: 'a.py', line: 1, reason: 'why', detailDeferred: false }];
    const { result } = renderHook(() => useHydratedCompliance(items), { wrapper: setup(get) });

    expect(result.current).toEqual(items);
    expect(get).not.toHaveBeenCalled();
  });

  it('keeps the slim items when the fetch fails', async () => {
    const get = vi.fn(async () => { throw new Error('down'); });
    const items = [slim('a.py', 1)];
    const { result } = renderHook(() => useHydratedCompliance(items), { wrapper: setup(get) });

    await waitFor(() => expect(get).toHaveBeenCalled());
    expect(result.current[0].file).toBe('a.py');
    expect(result.current[0].snippet).toBeNull();
  });
});
