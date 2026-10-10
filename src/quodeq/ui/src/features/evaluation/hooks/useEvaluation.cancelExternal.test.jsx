import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useEvaluation } from "./useEvaluation";
import { withQueryClient } from "../../../test-utils/withQueryClient.jsx";
import { ApiProvider } from "../../../api/ApiContext.jsx";
import { MockEventSource } from "../../../test-utils/MockEventSource.js";
import { chooseDialog } from "../../../utils/chooseDialog.js";
import { t } from "../../../strings/index.js";

// The stop dialog for an adopted external run says what else it ends.
vi.mock("../../../utils/chooseDialog.js", () => ({ chooseDialog: vi.fn().mockResolvedValue(null) }));

const nightly = { jobId: "ext-n", status: "running", source: "external", dimensions: [] };
const fakeApi = {
  getEvaluation: vi.fn(),
  startEvaluation: vi.fn(),
  cancelEvaluation: vi.fn(),
  listEvaluations: vi.fn(),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return <QueryWrapper><ApiProvider value={fakeApi}>{children}</ApiProvider></QueryWrapper>;
  };
}

describe("stopping an adopted external run", () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => { fn.mockReset(); });
    chooseDialog.mockClear();
    fakeApi.listEvaluations.mockResolvedValue([nightly]);
    fakeApi.getEvaluation.mockResolvedValue(nightly);
    vi.stubGlobal("EventSource", MockEventSource);
  });

  it("the dialog names the job it also ends", async () => {
    const { result } = renderHook(() => useEvaluation(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.job?.jobId).toBe("ext-n"));
    await act(async () => { await result.current.cancelEvaluation(); });
    expect(chooseDialog.mock.calls[0][0].message).toBe(t("evaluate.cancelBodyExternal"));
    expect(fakeApi.cancelEvaluation).not.toHaveBeenCalled();
  });
});
