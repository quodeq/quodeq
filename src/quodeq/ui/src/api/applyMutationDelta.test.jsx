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

  it("J: patches the RUN-SCOPED accumulated when isLatest (Overview reads scores(p, runId).accumulated)", () => {
    // When the user has drilled into a run, the app-root useDashboard reads
    // `accumulated` from the run-scoped scores query scores(p, runId), NOT the
    // null "latest" entry. That query has staleTime:Infinity, so if the dismiss
    // doesn't patch its accumulated it stays stale until a window-focus refetch.
    const { client, store, invalidateQueries } = makeClient();
    const runScopedKey = projectKeys.scores(PROJECT, RUN);
    const nullKey = projectKeys.scores(PROJECT, null);
    store.set(JSON.stringify(runScopedKey), {
      dimensions: [{ dimension: "maintainability", overallScore: "5.3", overallGrade: "C" }],
      accumulated: { dimensions: [{ dimension: "maintainability", overallGrade: "C" }], summary: {} },
      summary: {},
    });
    store.set(JSON.stringify(nullKey), { accumulated: { dimensions: [], summary: {} } });

    const newAccumulated = {
      dimensions: [{ dimension: "maintainability", overallGrade: "Good" }],
      summary: { overallGrade: "Good" },
    };
    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: newAccumulated,
      dimensions: [],
    });

    // The run-scoped entry the Overview actually reads must get the fresh rollup.
    expect(store.get(JSON.stringify(runScopedKey)).accumulated).toBe(newAccumulated);
    // Patched, not invalidated.
    const runAccInvalidated = invalidateQueries.mock.calls.some(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(runScopedKey),
    );
    expect(runAccInvalidated).toBe(false);
    // The null "latest" entry is still patched too (unchanged behavior).
    expect(store.get(JSON.stringify(nullKey)).accumulated).toBe(newAccumulated);
  });

  it("K: client-derive only rewrites dims the latest run OWNS (fromRunId === runId)", () => {
    const { client, store } = makeClient();
    const nullKey = projectKeys.scores(PROJECT, null);
    const runKey = projectKeys.scores(PROJECT, RUN);
    const OTHER = "run-old";
    const seed = () => ({
      accumulated: {
        dimensions: [
          { dimension: "security", fromRunId: RUN, overallScore: "5.0", overallGrade: "C" },
          { dimension: "maintainability", fromRunId: OTHER, overallScore: "7.0", overallGrade: "B" },
        ],
        summary: { overallGrade: "B", numericAverage: 6.0 },
      },
    });
    store.set(JSON.stringify(nullKey), seed());
    store.set(JSON.stringify(runKey), seed());

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      // The run rescore raises security AND reports maintainability, but the
      // accumulated maintainability entry belongs to a DIFFERENT run.
      dimensions: [
        { dimension: "security", overallScore: "6.5", overallGrade: "B" },
        { dimension: "maintainability", overallScore: "9.9", overallGrade: "A" },
      ],
    });

    for (const key of [nullKey, runKey]) {
      const acc = store.get(JSON.stringify(key)).accumulated;
      const sec = acc.dimensions.find((d) => d.dimension === "security");
      const maint = acc.dimensions.find((d) => d.dimension === "maintainability");
      // security is owned by RUN → derived from the run rescore.
      expect(sec.overallScore).toBe("6.5");
      expect(sec.overallGrade).toBe("B");
      // maintainability's accumulated entry comes from a different run → untouched
      // even though the rescore reported a value for it.
      expect(maint.overallScore).toBe("7.0");
      expect(maint.overallGrade).toBe("B");
      // weighted summary is deliberately left for a lazy refetch.
      expect(acc.summary.overallGrade).toBe("B");
    }
  });

  it("L: client-derive is a no-op (no invalidate) when the accumulated entry isn't cached", () => {
    const { client, setQueryData, invalidateQueries } = makeClient();
    const nullKey = projectKeys.scores(PROJECT, null);
    // scores(null) is NOT seeded — patchAccumulatedDims must not create or
    // invalidate it (an invalidate would trigger the slow cross-run refetch).
    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: true,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
    });
    const touched =
      setQueryData.mock.calls.some(([k]) => JSON.stringify(k) === JSON.stringify(nullKey)) ||
      invalidateQueries.mock.calls.some(
        ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(nullKey),
      );
    expect(touched).toBe(false);
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

// Slice 2: restore / delete / restore_all / delete_all all patch dim SCORES
// (like dismiss) but, because the client can't cheaply reconstruct the
// violation-list change, INVALIDATE the run-detail violation source instead of
// splicing. dismiss must keep splicing (regression).
describe("applyMutationDelta — restore/delete/bulk kinds (slice 2)", () => {
  function invalidatedNoRefetch(invalidateQueries, key) {
    return invalidateQueries.mock.calls.some(
      ([arg]) =>
        JSON.stringify(arg?.queryKey) === JSON.stringify(key) &&
        arg?.refetchType === "none",
    );
  }

  for (const kind of ["restore", "delete", "restore_all", "delete_all"]) {
    it(`${kind}: patches dashboard dim score`, () => {
      const { client, store } = makeClient();
      const key = projectKeys.dashboard(PROJECT, RUN);
      seedDashboard(store, key, [securityDim(), maintainabilityDim()]);

      applyMutationDelta(client, PROJECT, {
        kind,
        runId: RUN,
        isLatest: false,
        accumulated: null,
        dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
      });

      const sec = store
        .get(JSON.stringify(key))
        .dimensions.find((d) => d.dimension === "security");
      expect(sec.overallScore).toBe("6.5");
      expect(sec.overallGrade).toBe("B");
    });

    it(`${kind}: patches per-run scores dim score`, () => {
      const { client, store } = makeClient();
      const scoresKey = projectKeys.scores(PROJECT, RUN);
      store.set(JSON.stringify(scoresKey), {
        dimensions: [{ dimension: "security", overallScore: "5.0", overallGrade: "C" }],
        summary: {},
      });

      applyMutationDelta(client, PROJECT, {
        kind,
        runId: RUN,
        isLatest: false,
        accumulated: null,
        dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
      });

      const dim = store.get(JSON.stringify(scoresKey)).dimensions[0];
      expect(dim.overallScore).toBe("6.5");
      expect(dim.overallGrade).toBe("B");
    });

    it(`${kind}: INVALIDATES the run-detail violation source (does not splice)`, () => {
      const { client, store, invalidateQueries } = makeClient();
      const dashKey = projectKeys.dashboard(PROJECT, RUN);
      const scoresKey = projectKeys.scores(PROJECT, RUN);
      seedDashboard(store, dashKey, [securityDim()]);
      store.set(JSON.stringify(scoresKey), {
        dimensions: [{ dimension: "security", overallScore: "5.0", overallGrade: "C" }],
        summary: {},
      });

      applyMutationDelta(client, PROJECT, {
        kind,
        runId: RUN,
        isLatest: false,
        accumulated: null,
        dimensions: [],
      });

      // Both the dashboard and per-run scores violation sources are invalidated
      // with refetchType:"none" so lists refetch on next view.
      expect(invalidatedNoRefetch(invalidateQueries, dashKey)).toBe(true);
      expect(invalidatedNoRefetch(invalidateQueries, scoresKey)).toBe(true);

      // The dashboard violation list is NOT spliced in place — both violations
      // remain until the refetch replaces them.
      const sec = store.get(JSON.stringify(dashKey)).dimensions[0];
      expect(sec.violations).toHaveLength(2);
    });

    it(`${kind}: patches accumulated (null AND run-scoped) when isLatest`, () => {
      const { client, store, invalidateQueries } = makeClient();
      const accKey = projectKeys.scores(PROJECT, null);
      const runScopedKey = projectKeys.scores(PROJECT, RUN);
      store.set(JSON.stringify(accKey), { accumulated: { dimensions: [], summary: {} } });
      store.set(JSON.stringify(runScopedKey), {
        dimensions: [{ dimension: "security", overallScore: "5.0", overallGrade: "C" }],
        accumulated: { dimensions: [], summary: {} },
        summary: {},
      });

      const newAccumulated = {
        dimensions: [{ dimension: "security" }],
        summary: { overallGrade: "B" },
      };
      applyMutationDelta(client, PROJECT, {
        kind,
        runId: RUN,
        isLatest: true,
        accumulated: newAccumulated,
        dimensions: [],
      });

      expect(store.get(JSON.stringify(accKey)).accumulated).toBe(newAccumulated);
      // The run-scoped entry the Overview reads while drilled into a run must
      // also get the fresh rollup — see test J.
      expect(store.get(JSON.stringify(runScopedKey)).accumulated).toBe(newAccumulated);
      const accInvalidated = invalidateQueries.mock.calls.some(
        ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(accKey),
      );
      expect(accInvalidated).toBe(false);
    });

    it(`${kind}: untouched dimension keeps referential identity in score-patch`, () => {
      const { client, store } = makeClient();
      const scoresKey = projectKeys.scores(PROJECT, RUN);
      const prevDims = [
        { dimension: "security", overallScore: "5.0", overallGrade: "C" },
        { dimension: "maintainability", overallScore: "7.0", overallGrade: "B" },
      ];
      store.set(JSON.stringify(scoresKey), { dimensions: prevDims, summary: {} });

      applyMutationDelta(client, PROJECT, {
        kind,
        runId: RUN,
        isLatest: false,
        accumulated: null,
        dimensions: [{ dimension: "security", overallScore: "6.5", overallGrade: "B" }],
      });

      const next = store.get(JSON.stringify(scoresKey));
      // maintainability was not rescored → same object reference.
      expect(next.dimensions[1]).toBe(prevDims[1]);
    });
  }

  it("dismiss still SPLICES the violation (regression, not invalidate)", () => {
    const { client, store, invalidateQueries } = makeClient();
    const dashKey = projectKeys.dashboard(PROJECT, RUN);
    seedDashboard(store, dashKey, [securityDim()]);

    applyMutationDelta(client, PROJECT, {
      kind: "dismiss",
      runId: RUN,
      isLatest: false,
      dismissed: { req: "R1", file: "a.py", line: 10 },
      accumulated: null,
      dimensions: [],
    });

    const sec = store.get(JSON.stringify(dashKey)).dimensions[0];
    // Spliced in place, not left for a refetch.
    expect(sec.violations.map((v) => v.req)).toEqual(["R2"]);
    expect(sec.totals.violationCount).toBe(1);
    // dismiss must NOT invalidate the dashboard violation source.
    const dashInvalidated = invalidateQueries.mock.calls.some(
      ([arg]) => JSON.stringify(arg?.queryKey) === JSON.stringify(dashKey),
    );
    expect(dashInvalidated).toBe(false);
  });
});
