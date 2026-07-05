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

function maintainabilityDim() {
  return {
    dimension: "maintainability",
    overallScore: "7.0",
    overallGrade: "B",
    violations: [],
    totals: { violationCount: 0, severity: { critical: 0, major: 0, minor: 0 } },
  };
}

describe("applyMutationDelta", () => {
  it("A: patches the dimension score from the rescored dims", () => {
    const { client, store, setQueryData } = makeClient();
    const key = projectKeys.dashboard(PROJECT, RUN);
    seedDashboard(store, key, [securityDim(), maintainabilityDim()]);

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

  it("B: removes the dismissed finding and decrements totals", () => {
    const { client, store } = makeClient();
    const key = projectKeys.dashboard(PROJECT, RUN);
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

  it("E: invalidates (refetchType none) when dashboard cache is absent, no setQueryData", () => {
    const { client, setQueryData, invalidateQueries } = makeClient();
    const dashKey = projectKeys.dashboard(PROJECT, RUN);

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

  it("F: invalidates accumulated when delta.accumulated is null", () => {
    const { client, store, invalidateQueries, setQueryData } = makeClient();
    const scoresKey = projectKeys.scores(PROJECT, null);
    store.set(JSON.stringify(scoresKey), { accumulated: { dimensions: [] } });

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [],
    });

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: scoresKey });
    const setAcc = setQueryData.mock.calls.some(
      ([k]) => JSON.stringify(k) === JSON.stringify(scoresKey),
    );
    expect(setAcc).toBe(false);
  });

  it("G: isLatest false leaves dashboard('latest') and scores(null) untouched", () => {
    const { client, setQueryData, invalidateQueries } = makeClient();
    const latestDashKey = projectKeys.dashboard(PROJECT, "latest");
    const accKey = projectKeys.scores(PROJECT, null);

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: { dimensions: [] },
      dimensions: [],
    });

    const touched = (key) =>
      setQueryData.mock.calls.some(([k]) => JSON.stringify(k) === JSON.stringify(key)) ||
      invalidateQueries.mock.calls.some(
        ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(key),
      );
    expect(touched(latestDashKey)).toBe(false);
    expect(touched(accKey)).toBe(false);
  });

  it("H: unknown dim in delta leaves existing dims unchanged and does not throw", () => {
    const { client, store } = makeClient();
    const key = projectKeys.dashboard(PROJECT, RUN);
    seedDashboard(store, key, [securityDim(), maintainabilityDim()]);

    expect(() =>
      applyMutationDelta(client, PROJECT, {
        kind: "dismiss",
        runId: RUN,
        isLatest: false,
        dismissed: { req: "ZZZ", file: "nope.py", line: 999 },
        accumulated: null,
        dimensions: [{ dimension: "does-not-exist", overallScore: "9.9", overallGrade: "A" }],
      }),
    ).not.toThrow();

    const next = store.get(JSON.stringify(key));
    const sec = next.dimensions.find((d) => d.dimension === "security");
    // Unknown-dim rescore doesn't touch security; no violation matched either.
    expect(sec.overallScore).toBe("5.0");
    expect(sec.violations).toHaveLength(2);
  });

  it("I: untouched dimension keeps referential identity", () => {
    const { client, store } = makeClient();
    const key = projectKeys.dashboard(PROJECT, RUN);
    const prevDims = [securityDim(), maintainabilityDim()];
    seedDashboard(store, key, prevDims);

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
    });

    const next = store.get(JSON.stringify(key));
    // maintainability was neither rescored nor had a violation removed →
    // it must be the same object reference.
    expect(next.dimensions[1]).toBe(prevDims[1]);
  });
});
