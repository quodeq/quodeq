import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { withQueryClient } from "./withQueryClient";

describe("withQueryClient", () => {
  it("provides a QueryClient that resolves a queryFn", async () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(
      () => useQuery({ queryKey: ["t"], queryFn: () => Promise.resolve(42) }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.data).toBe(42));
  });

  it("returns a fresh wrapper each call (no state leak between tests)", () => {
    const wrapperA = withQueryClient();
    const wrapperB = withQueryClient();
    expect(wrapperA).not.toBe(wrapperB);
  });

  it("disables retries so failing queryFns surface errors immediately", async () => {
    const wrapper = withQueryClient();
    const { result } = renderHook(
      () => useQuery({
        queryKey: ["err"],
        queryFn: () => Promise.reject(new Error("boom")),
      }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
