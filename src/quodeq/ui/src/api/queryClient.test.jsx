import { describe, it, expect } from "vitest";
import { queryClient } from "./queryClient";

describe("queryClient", () => {
  it("is a QueryClient instance", () => {
    expect(typeof queryClient.getQueryData).toBe("function");
    expect(typeof queryClient.setQueryData).toBe("function");
    expect(typeof queryClient.invalidateQueries).toBe("function");
  });

  it("defaults staleTime to 30s", () => {
    expect(queryClient.getDefaultOptions().queries.staleTime).toBe(30_000);
  });

  it("defaults retry to 1", () => {
    expect(queryClient.getDefaultOptions().queries.retry).toBe(1);
  });

  it("defaults refetchOnWindowFocus to true", () => {
    expect(queryClient.getDefaultOptions().queries.refetchOnWindowFocus).toBe(true);
  });

  it("defaults refetchOnReconnect to true", () => {
    expect(queryClient.getDefaultOptions().queries.refetchOnReconnect).toBe(true);
  });
});
