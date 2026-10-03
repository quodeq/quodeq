import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// The status query's polling path, which SSE_ENABLED (read once at import)
// turns off by default. Pin the flag before the hook is imported. Findings
// never poll: the test writes them into the cache slot the stream fills.
vi.hoisted(() => { import.meta.env.VITE_USE_SSE_EVENTS = 'false'; });

import { render, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { evaluationKeys } from '../../api/queryKeys.js';

vi.mock('../../api/index.js', () => ({
  getEvaluationProgress: vi.fn(),
}));
import { getEvaluationProgress } from '../../api/index.js';

import { ApiProvider } from '../../api/ApiContext.jsx';
import { EvaluationLiveProvider, useLiveJob, useLiveFindings, useEvaluationActions } from './EvaluationLiveContext.jsx';
import { createLiveEvaluationStore } from './liveEvaluationStore.js';
import { countCommits } from '../../test-utils/budgets.jsx';

// A poll tick must not reach the page the user is on. The live values are
// published to a store, so only the components that read them re-render; a
// page that reads none of them commits zero times for the whole run.

const POLL_TICK_MS = 2000;
const TICKS = 10;
const RUNNING_JOB = {
  jobId: 'job-1', status: 'running',
  outputProject: 'project-a', outputRunId: 'run-1', dimensions: ['security'],
};
const PROGRESS = {
  currentDimension: 'security',
  dimensions: [{ id: 'security', state: 'running', files: { taken: 3, total: 10 } }],
  totalElapsedS: 12,
};

function makeFakeApi() {
  return {
    listEvaluations: vi.fn(async () => [RUNNING_JOB]),
    getEvaluation: vi.fn(async () => RUNNING_JOB),
  };
}

// One more finding per tick, the way the stream appends them to the cache
// slot (see useRunEventStream's finding handler).
function streamOneFinding(client, n) {
  const row = { principle: 'Authenticity', file: `a${n}.py`, line: n + 1, severity: 'major', dimension: 'security' };
  client.setQueryData(evaluationKeys.findings(RUNNING_JOB.jobId), (prev = []) => [...prev, row]);
}

function makeEvaluationDeps() {
  return {
    navigation: { navTab: vi.fn(), navReset: vi.fn() },
    projects: { loadProjects: vi.fn(async () => []), setProjects: vi.fn(), selectProjectAndRun: vi.fn() },
    selectedProject: 'project-a',
  };
}

// Stands for any page the user can be on: it can start or cancel a run, but
// reads none of the live values.
function PageWithoutLiveState() {
  const actions = useEvaluationActions();
  return <button type="button" data-testid="page" onClick={actions.cancelEvaluation}>x</button>;
}

// Stands for the job strip: it reads the job and its findings.
function LiveStrip() {
  const job = useLiveJob();
  const findings = useLiveFindings('security');
  return <div data-testid="strip">{`${job?.status || 'idle'}:${findings.length}`}</div>;
}

function renderShell(store, page, strip, client) {
  return render(
    <QueryClientProvider client={client}>
      <ApiProvider value={makeFakeApi()}>
        <EvaluationLiveProvider store={store} {...makeEvaluationDeps()}>
          <page.Counted />
          <strip.Counted />
        </EvaluationLiveProvider>
      </ApiProvider>
    </QueryClientProvider>
  );
}

describe('live evaluation render budget', () => {
  beforeEach(() => {
    getEvaluationProgress.mockReset();
    getEvaluationProgress.mockResolvedValue(PROGRESS);
  });
  afterEach(() => { vi.useRealTimers(); });

  it('a poll tick re-renders the live strip and never the page', async () => {
    const store = createLiveEvaluationStore();
    const page = countCommits(PageWithoutLiveState);
    const strip = countCommits(LiveStrip);
    // Fake timers before the render: React Query's poll timers are armed on
    // mount, and a real timer armed first would never be advanced here.
    vi.useFakeTimers();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = renderShell(store, page, strip, client);

    // The run is adopted on mount, the way a CLI-started job is; the first
    // findings land a tick later, once the job is known.
    for (let i = 0; i < 3; i += 1) {
      // eslint-disable-next-line no-await-in-loop -- ticks are sequential by design
      await act(async () => { await vi.advanceTimersByTimeAsync(POLL_TICK_MS); });
      streamOneFinding(client, i);
    }
    expect(store.getState().job?.status).toBe('running');
    expect(view.getByTestId('strip').textContent).toMatch(/^running:[1-9]/);

    page.reset();
    strip.reset();
    for (let i = 0; i < TICKS; i += 1) {
      // eslint-disable-next-line no-await-in-loop -- ticks are sequential by design
      await act(async () => {
        streamOneFinding(client, 3 + i);
        await vi.advanceTimersByTimeAsync(POLL_TICK_MS);
      });
    }

    expect(page.commits()).toBe(0);
    // One commit per tick, and only in the component that reads the values.
    expect(strip.commits()).toBe(TICKS);
  });
});
