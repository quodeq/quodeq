import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useByTypeData } from './useByTypeData.js';

function Probe({ project, dimensions, selectedSource }) {
  const { diffsByRun, standardsByDim, loading } = useByTypeData({ project, dimensions, selectedSource });
  return <pre data-testid="out">{JSON.stringify({ runs: Object.keys(diffsByRun).sort(), dims: Object.keys(standardsByDim).sort(), loading })}</pre>;
}

function mount(api, dimensions, selectedSource) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ApiProvider value={api}><Probe project="p" dimensions={dimensions} selectedSource={selectedSource} /></ApiProvider></QueryClientProvider>);
}

describe('useByTypeData', () => {
  it('fetches one diff per distinct run and one standard per dimension', async () => {
    const calls = { diff: [], std: [] };
    const api = {
      getRunDiff: async (p, run) => { calls.diff.push(run); return { runId: run, dimensions: {} }; },
      getStandard: async (id) => { calls.std.push(id); return { id, principles: [] }; },
    };
    mount(api, [{ dimension: 'maintainability', fromRunId: 'r1' }, { dimension: 'security', fromRunId: 'r1' }, { dimension: 'usability', fromRunId: 'r2' }]);
    await screen.findByText(/"loading":false/);
    expect(calls.diff.sort()).toEqual(['r1', 'r2']);
    expect(calls.std.sort()).toEqual(['maintainability', 'security', 'usability']);
    expect(screen.getByTestId('out').textContent).toContain('"runs":["r1","r2"]');
  });

  it('a failed diff leaves that run out and does not block the others', async () => {
    const api = {
      getRunDiff: async (p, run) => { if (run === 'r2') throw new Error('boom'); return { runId: run, dimensions: {} }; },
      getStandard: async (id) => ({ id, principles: [] }),
    };
    mount(api, [{ dimension: 'a', fromRunId: 'r1' }, { dimension: 'b', fromRunId: 'r2' }]);
    await screen.findByText(/"loading":false/);
    expect(screen.getByTestId('out').textContent).toContain('"runs":["r1"]');
  });

  it('a shared project fetches standards but no diffs, and is not loading forever', async () => {
    const calls = { diff: [], std: [] };
    const api = {
      getRunDiff: async (p, run) => { calls.diff.push(run); return { runId: run, dimensions: {} }; },
      getStandard: async (id) => { calls.std.push(id); return { id, principles: [] }; },
    };
    mount(api, [{ dimension: 'a', fromRunId: 'r1' }], 'shared');
    await screen.findByText(/"loading":false/);
    expect(calls.diff).toEqual([]);
    expect(calls.std).toEqual(['a']);
  });
});
