/**
 * useEvaluation's start/cancel mutations.
 *
 * Split out of useEvaluation.js (see that file's header for the hook's
 * overall data-flow doc). Moved verbatim: mutationFn/onSuccess/onError
 * bodies are additionally factored into named functions (still
 * logic-identical) so useEvaluationMutations itself clears the
 * max-lines-per-function gate.
 */
import { useMutation } from "@tanstack/react-query";
import { evaluationKeys, projectKeys } from "../../../api/queryKeys.js";
import { t } from "../../../strings/index.js";
import { apiErrorMessage } from "../../../strings/apiErrors.js";
import { preparePayload } from "./useEvaluation.helpers.js";

function startMutationFn(api) {
  return (input) => {
    // uiProject is client-side bookkeeping (which project launched this
    // job) — strip it so it never reaches the HTTP payload.
    const { uiProject, ...rest } = input;
    // preparePayload throws on missing provider/model — let the error
    // propagate to onError so jobError gets set with a useful message.
    const prepared = preparePayload(rest);
    return api.startEvaluation(prepared).then((created) => ({
      ...created,
      repo: prepared.repo,
      uiProject,
    }));
  };
}

function startOnSuccess({ queryClient, setJobError, setJobId, setStartedProject }) {
  return (created) => {
    setJobError(null);
    setJobId(created.jobId);
    setStartedProject(created.uiProject || null);
    queryClient.setQueryData(evaluationKeys.status(created.jobId), created);
    // Invalidate the project subtree so History (and any other view backed
    // by project queries) shows the freshly-started run as 'running'
    // immediately, instead of waiting for the next poll tick. Without
    // this, History stays stale until the user navigates away and back,
    // or the polling timer fires -- user-visible delay was ~10-30s on a
    // fresh start.
    queryClient.invalidateQueries({ queryKey: projectKeys.all() });
  };
}

function startOnError(setJobError) {
  // Our own prereq errors carry copy written for the user. Server
  // rejections go through apiErrorMessage: a mapped code wins (translated),
  // otherwise the backend's specific sentence (e.g. an invalid aiCmdPath
  // override names the binary it could not find), and the generic string
  // is only for failures with no text at all.
  return (err) => {
    setJobError(err?.userFacing ? err.message : apiErrorMessage(err, "evaluate.startFailed"));
  };
}

function cancelOnSuccess({ queryClient, jobId, setJobId, setStartedProject }) {
  return (_data, variables) => {
    if (variables?.discard) {
      // Discard deletes the run server-side (dir + index row + job entry),
      // so any further status poll would 404. Drop the job and its cached
      // queries right away instead of waiting for a terminal status that
      // will never arrive.
      if (jobId) {
        queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(jobId) });
      }
      setJobId(null);
      setStartedProject(null);
    } else if (jobId) {
      queryClient.invalidateQueries({ queryKey: evaluationKeys.evaluation(jobId) });
    }
    // Mirror startMutation: refresh the project subtree so History's
    // availableRuns drops the cancelled run from the in-progress list
    // immediately. Without this, the History row stays on the 'performing
    // an evaluation...' placeholder until the next polling tick (or, under
    // SSE, the terminal-status event from the stream).
    queryClient.invalidateQueries({ queryKey: projectKeys.all() });
  };
}

function cancelOnError({ queryClient, jobId, setJobId, setJobError }) {
  // The backend returns 409 when the job is no longer cancellable (process
  // gone, status already terminal) and 404 when it is unknown. Only those
  // mean the job is really over — clear it so the panel closes. A
  // transient failure (500, network, the 30s request timeout racing the
  // ~33s server-side kill path) must KEEP the job: clearing it hid a
  // still-running scan and let a second concurrent scan start on the same
  // project.
  // Keep the backend's sentence as a detail suffix: a 409 ("already
  // finished") and a 500 are different situations for the user, and the
  // translated summary alone flattened them into one. Same policy as
  // apiErrorMessage, which preserves err.message for unmapped codes.
  return (err) => {
    setJobError(err?.message ? `${t("evaluate.cancelFailed")} (${err.message})` : t("evaluate.cancelFailed"));
    if (err?.status !== 409 && err?.status !== 404) return;
    const id = jobId;
    if (id) queryClient.removeQueries({ queryKey: evaluationKeys.evaluation(id) });
    setJobId(null);
  };
}

export function useEvaluationMutations({ api, queryClient, jobId, setJobId, setJobError, setStartedProject }) {
  const startMutation = useMutation({
    mutationFn: startMutationFn(api),
    onSuccess: startOnSuccess({ queryClient, setJobError, setJobId, setStartedProject }),
    onError: startOnError(setJobError),
  });

  const cancelMutation = useMutation({
    mutationFn: ({ discard } = {}) => api.cancelEvaluation(jobId, { discard }),
    onSuccess: cancelOnSuccess({ queryClient, jobId, setJobId, setStartedProject }),
    onError: cancelOnError({ queryClient, jobId, setJobId, setJobError }),
  });

  return { startMutation, cancelMutation };
}
