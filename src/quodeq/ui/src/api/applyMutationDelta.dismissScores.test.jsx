import { describe, it, expect, vi } from "vitest";
import { applyMutationDelta } from "./applyMutationDelta";
import { projectKeys } from "./queryKeys";

// A mock queryClient backed by a Map keyed by JSON.stringify(key), so tests
// can seed caches and assert on the patched result. getQueryData/setQueryData
// mirror React Query's functional-updater contract.
function makeClient(initial = {}) {
  const store = new Map(Object.entries(initial));
  const getQueryData = vi.fn((key) => store.get(JSON.stringify(key)));
  const setQueryData = vi.fn((key, updater) => {
    const k = JSON.stringify(key);
    const prev = store.get(k);
    const next = typeof updater === "function" ? updater(prev) : updater;
    store.set(k, next);
    return next;
  });
  const invalidateQueries = vi.fn();
  return {
    client: { getQueryData, setQueryData, invalidateQueries },
    store,
    getQueryData,
    setQueryData,
    invalidateQueries,
  };
}

const PROJECT = "p1";
const RUN = "run-1";

function seedDashboard(store, key, dimensions) {
  store.set(JSON.stringify(key), { dimensions });
}

// A dashboard dimension carrying two violations + totals, so removal tests
// have something to splice.
function securityDim() {
  return {
    dimension: "security",
    overallScore: "5.0",
    overallGrade: "C",
    violations: [
      { req: "R1", file: "a.py", line: 10, severity: "critical" },
      { req: "R2", file: "b.py", line: 20, severity: "major" },
    ],
    totals: {
      violationCount: 2,
      severity: { critical: 1, major: 1, minor: 0 },
    },
  };
}

// The run page's overview dashboard dimension: counts, no lists.
function overviewDim() {
  const { violations, ...rest } = securityDim();
  return rest;
}

const overviewKey = (run) => projectKeys.dashboard(PROJECT, run, "local");

function maintainabilityDim() {
  return {
    dimension: "maintainability",
    overallScore: "7.0",
    overallGrade: "B",
    violations: [],
    totals: { violationCount: 0, severity: { critical: 0, major: 0, minor: 0 } },
  };
}


// Split from applyMutationDelta.test.jsx: dismiss-kind dashboard/scores
// score patching, accumulated patching, and the dashboard-cache-absent
// invalidate path.

describe("applyMutationDelta", () => {
  it("A: patches the overview dashboard's dimension score from the rescored dims", () => {
    const { client, store, setQueryData } = makeClient();
    const key = overviewKey(RUN);
    seedDashboard(store, key, [overviewDim(), maintainabilityDim()]);

    const delta = {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [
        { dimension: "security", overallScore: "6.5", overallGrade: "B" },
      ],
    };

    applyMutationDelta(client, PROJECT, delta);

    expect(setQueryData).toHaveBeenCalled();
    const next = store.get(JSON.stringify(key));
    const sec = next.dimensions.find((d) => d.dimension === "security");
    expect(sec.overallScore).toBe("6.5");
    expect(sec.overallGrade).toBe("B");
  });

  it("B: removes the dismissed finding from the run findings and decrements totals", () => {
    const { client, store } = makeClient();
    const key = projectKeys.runScores(PROJECT, RUN);
    seedDashboard(store, key, [securityDim()]);

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [],
    });

    const sec = store.get(JSON.stringify(key)).dimensions[0];
    expect(sec.violations.map((v) => v.req)).toEqual(["R2"]);
    expect(sec.totals.violationCount).toBe(1);
    expect(sec.totals.severity.critical).toBe(0);
    expect(sec.totals.severity.major).toBe(1);
  });

  it("C: patches accumulated (not invalidate) when isLatest", () => {
    const { client, store, invalidateQueries } = makeClient();
    const scoresKey = projectKeys.scores(PROJECT, null);
    store.set(JSON.stringify(scoresKey), { accumulated: { dimensions: [], summary: {} } });

    const newAccumulated = { dimensions: [{ dimension: "security" }], summary: { overallGrade: "B" } };
    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: newAccumulated,
      dimensions: [],
    });

    expect(store.get(JSON.stringify(scoresKey)).accumulated).toBe(newAccumulated);
    // Accumulated must be patched, not invalidated.
    const accInvalidated = invalidateQueries.mock.calls.some(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(scoresKey),
    );
    expect(accInvalidated).toBe(false);
  });

  it("D: updates the per-run scores dim score", () => {
    const { client, store } = makeClient();
    const scoresKey = projectKeys.scores(PROJECT, RUN);
    store.set(JSON.stringify(scoresKey), {
      dimensions: [{ dimension: "security", overallScore: "5.0", overallGrade: "C" }],
      summary: {},
    });

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
    });

    const dim = store.get(JSON.stringify(scoresKey)).dimensions[0];
    expect(dim.overallScore).toBe("6.5");
    expect(dim.overallGrade).toBe("B");
  });

  it("B2: the server's recounted totals win over the local decrement", () => {
    const { client, store } = makeClient();
    const key = projectKeys.runScores(PROJECT, RUN);
    seedDashboard(store, key, [securityDim()]);
    const totals = { violationCount: 1, severity: { critical: 0, major: 1, minor: 0 }, complianceCount: 4 };

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B", totals }],
    });

    const sec = store.get(JSON.stringify(key)).dimensions[0];
    expect(sec.violations.map((v) => v.req)).toEqual(["R2"]);
    expect(sec.totals).toEqual(totals);
  });

  it("B3: the overview dashboard (no lists) takes the recounted totals", () => {
    const { client, store } = makeClient();
    const key = overviewKey(RUN);
    seedDashboard(store, key, [overviewDim()]);
    const totals = { violationCount: 1, severity: { critical: 0, major: 1, minor: 0 } };

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B", totals }],
    });

    const sec = store.get(JSON.stringify(key)).dimensions[0];
    expect(sec.violations).toBeUndefined();
    expect(sec.totals).toEqual(totals);
    expect(sec.overallGrade).toBe("B");
  });

  it("E: invalidates (refetchType none) when the overview cache is absent, no setQueryData", () => {
    const { client, setQueryData, invalidateQueries } = makeClient();
    const dashKey = overviewKey(RUN);

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
    });

    // Dashboard was absent → invalidate with refetchType:"none".
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: dashKey, refetchType: "none" });
    // No setQueryData for the dashboard key.
    const setDash = setQueryData.mock.calls.some(
      ([k]) => JSON.stringify(k) === JSON.stringify(dashKey),
    );
    expect(setDash).toBe(false);
  });

  it("F: client-derives accumulated dims (does NOT invalidate) when delta.accumulated is null", () => {
    // The mutation deltas no longer carry a server rollup; the accumulated
    // dimension grades are derived from the per-run rescore instead. Crucially
    // this must NOT invalidate the accumulated query — that would trigger the
    // slow cross-run refetch this whole change exists to avoid.
    const { client, store, invalidateQueries } = makeClient();
    const scoresKey = projectKeys.scores(PROJECT, null);
    store.set(JSON.stringify(scoresKey), {
      accumulated: {
        dimensions: [{ dimension: "security", fromRunId: RUN, overallScore: "5.0", overallGrade: "C" }],
        summary: { overallGrade: "C" },
      },
    });

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
    });

    const acc = store.get(JSON.stringify(scoresKey)).accumulated;
    // The run-owned dim is derived from the rescore; summary left for a lazy refetch.
    expect(acc.dimensions[0].overallScore).toBe("6.5");
    expect(acc.dimensions[0].overallGrade).toBe("B");
    expect(acc.summary.overallGrade).toBe("C");
    const invalidated = invalidateQueries.mock.calls.some(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(scoresKey),
    );
    expect(invalidated).toBe(false);
  });

  it("patches the overview latest entry's score when the run is the latest", () => {
    const { client, store } = makeClient();
    const latestKey = overviewKey("latest");
    seedDashboard(store, latestKey, [overviewDim()]);
    const totals = { violationCount: 2, severity: { critical: 0, major: 1, minor: 1 } };

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B", totals }],
    });

    const sec = store.get(JSON.stringify(latestKey)).dimensions[0];
    expect(sec.overallScore).toBe("6.5");
    expect(sec.totals).toEqual(totals);
  });
});
