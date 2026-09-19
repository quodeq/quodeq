import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useEvaluationQueries } from "./useEvaluationQueries.js";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";

// The polling path is what the evaluation screen runs on by default
// (VITE_USE_SSE_EVENTS off). It fetches each dimension's eval and hands the
// rows to the live feed, which reads `principle` — a field the backend has
// never emitted. It emits `practiceId`, on the report path and on the live
// evidence path alike, so a raw spread reached the feed with no rule to show.

const REPORT_ROW = {
  practiceId: "Authenticity",
  req: "S-AUT-3",
  file: "src/quodeq/api/_assistant_helpers.py",
  line: 116,
  severity: "minor",
  title: "Path traversal via project_uuid",
  snippet: "Path(session[\"project_uuid\"])",
  reqRefs: [{ label: "CWE-22", url: "https://cwe.mitre.org/data/definitions/22.html" }],
  confidence: 25,
};

function makeApi(violations) {
  return {
    getEvaluation: vi.fn().mockResolvedValue({
      jobId: "job-1",
      status: "running",
      outputProject: "proj",
      outputRunId: "run-1",
      dimensions: ["security"],
    }),
    getDimensionEval: vi.fn().mockResolvedValue({ violations }),
  };
}

function renderQueries(api) {
  const QC = withQueryClient();
  return renderHook(() => useEvaluationQueries(api, "job-1"), { wrapper: QC });
}

describe("useEvaluationQueries findings mapping", () => {
  it("exposes the backend's practiceId as `principle`", async () => {
    const { result } = renderQueries(makeApi([REPORT_ROW]));
    await waitFor(() => expect(result.current.liveViolations.security).toHaveLength(1));
    expect(result.current.liveViolations.security[0].principle).toBe("Authenticity");
  });

  it("keeps wire-only fields the canonical model does not carry", async () => {
    const { result } = renderQueries(makeApi([REPORT_ROW]));
    await waitFor(() => expect(result.current.liveViolations.security).toHaveLength(1));
    expect(result.current.liveViolations.security[0].confidence).toBe(25);
  });

  it("tags each row with the dimension it was fetched for", async () => {
    const { result } = renderQueries(makeApi([REPORT_ROW]));
    await waitFor(() => expect(result.current.liveViolations.security).toHaveLength(1));
    expect(result.current.liveViolations.security[0].dimension).toBe("security");
  });

  it("gives two findings on one line distinct identities", async () => {
    // The feed keys rows on `${dim}-${file}-${principle}-${line}`. With
    // principle undefined on every row, two findings raised against the same
    // line under different principles collapsed onto one React key.
    const second = { ...REPORT_ROW, practiceId: "Integrity", req: "S-INT-1" };
    const { result } = renderQueries(makeApi([REPORT_ROW, second]));
    await waitFor(() => expect(result.current.liveViolations.security).toHaveLength(2));
    const principles = result.current.liveViolations.security.map((v) => v.principle);
    expect(new Set(principles).size).toBe(2);
  });

  it("survives a dimension eval that carries no violations", async () => {
    const { result } = renderQueries(makeApi(undefined));
    await waitFor(() => expect(result.current.job).not.toBeNull());
    expect(result.current.liveViolations).toEqual({});
  });
});
