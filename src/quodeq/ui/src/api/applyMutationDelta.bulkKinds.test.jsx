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


// Split from applyMutationDelta.test.jsx: restore/delete/restore_all/
// delete_all kinds (slice 2), which invalidate the violation source
// instead of splicing.

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
