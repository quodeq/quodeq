import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { QueryClientProvider, onlineManager, useQuery } from "@tanstack/react-query";
import { queryClient } from "./queryClient";
import { ERROR_RETRY_MS, refetchWhileError } from "../hooks/queryDefaults.js";

// The API lives on 127.0.0.1, so the browser's idea of being "online" (its
// route to the internet) says nothing about whether a fetch can succeed.
// react-query's default networkMode gates every fetch on that signal: after
// the webview fires `offline` (Wi-Fi drop, sleep, VPN flip), each refetch
// parks as fetchStatus 'paused' and waits for an `online` event that WebKit
// does not always deliver. A query that had already failed then keeps its
// error -- the Overview's "Failed to load dashboard data" line -- for as long
// as the window stays open, with the server answering the whole time. These
// tests use the production client so its defaults are what is under test.

function Wrapper({ children }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

afterEach(() => {
  onlineManager.setOnline(true);
  queryClient.clear();
  vi.useRealTimers();
});

describe("queryClient on a localhost API", () => {
  it("never pauses queries or mutations on the browser's online signal", () => {
    const { queries, mutations } = queryClient.getDefaultOptions();
    expect(queries.networkMode).toBe("always");
    expect(mutations.networkMode).toBe("always");
  });

  it("keeps fetching while the browser reports offline", async () => {
    vi.useFakeTimers();
    onlineManager.setOnline(false);
    const queryFn = vi.fn(async () => "payload");

    const { result } = renderHook(
      () => useQuery({ queryKey: ["localhost", "offline-fetch"], queryFn }),
      { wrapper: Wrapper },
    );
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });

    expect(queryFn).toHaveBeenCalledTimes(1);
    expect(result.current.fetchStatus).not.toBe("paused");
    expect(result.current.data).toBe("payload");
  });

  it("clears an error through the error-retry interval while the browser reports offline", async () => {
    vi.useFakeTimers();
    const state = { fail: true };
    const queryFn = vi.fn(async () => {
      if (state.fail) throw new Error("Load failed");
      return "payload";
    });

    const { result } = renderHook(
      () => useQuery({ queryKey: ["localhost", "offline-recovery"], queryFn, refetchInterval: refetchWhileError }),
      { wrapper: Wrapper },
    );
    // First attempt plus the production client's single retry (1s delay).
    await act(async () => { await vi.advanceTimersByTimeAsync(1_500); });
    expect(result.current.isError).toBe(true);

    // The webview now says offline; the server comes back. Only the
    // error-retry interval can clear the error, and it must not pause.
    onlineManager.setOnline(false);
    state.fail = false;
    await act(async () => { await vi.advanceTimersByTimeAsync(ERROR_RETRY_MS + 100); });

    expect(result.current.fetchStatus).not.toBe("paused");
    expect(result.current.isError).toBe(false);
    expect(result.current.data).toBe("payload");
  });
});
