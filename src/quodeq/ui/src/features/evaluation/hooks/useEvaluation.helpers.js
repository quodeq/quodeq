/**
 * useEvaluation helpers: poll-interval policy and start-payload prep.
 *
 * Split out of useEvaluation.js (see that file's header for the hook's
 * overall data-flow doc). Kept logic-identical to the pre-split version.
 */
import { ACTIVE_PROVIDER_KEY, providerKey } from "../../../constants.js";
import { resolveProviderSettings } from "../../../utils/effectiveProviderSettings.js";
import { t } from "../../../strings/index.js";
import { STREAM_STATE } from "./runEventSourceRegistry.js";

export const JOB_POLL_MS = 1500;
// While no run is held, how often to check for one that started elsewhere
// (the nightly, a PR review, a terminal run).
export const ADOPT_POLL_MS = 15_000;
// The status query still refetches, slowly, as a safety net against a frame
// the stream dropped or a server that never sent one.
export const SSE_STATUS_SAFETY_NET_MS = 10_000;

/**
 * Poll interval for the job status query. Exported for tests.
 *
 * The stream feeds the cache, so the query only refetches on a slow safety
 * net, except while the stream is in error: then the fast poll takes over
 * until it reconnects, so a dropped connection never leaves the screen
 * frozen on a stale job.
 */
export function statusRefetchInterval(streamState) {
  if (streamState === STREAM_STATE.ERROR) return JOB_POLL_MS;
  return SSE_STATUS_SAFETY_NET_MS;
}

/**
 * An error whose message is meant for the user, not the console.
 *
 * The flag is what makes it safe to translate: the mutation's onError used
 * to decide by sniffing the message text (`msg.startsWith("No ")`), which
 * silently stops matching the moment the copy is translated or reworded.
 */
function userFacingError(key) {
  const err = new Error(t(key));
  err.userFacing = true;
  return err;
}

/**
 * Merge per-provider Settings (provider, model, subagents, budget, etc.)
 * from localStorage into the start-evaluation payload.
 *
 * Caller-provided values win: a wizard launch names its provider/model and
 * time limit explicitly, and those must not be silently overwritten by the
 * active tab's Settings (the wizard's TIME LIMIT field used to be dead
 * code because of exactly that). Per-provider settings are read from the
 * payload's provider when one is named. Unset keys resolve through
 * resolveProviderSettings — the same source of truth the Settings screen
 * and the Evaluate header display. The payload never carries an API key:
 * the backend resolves it from its own secure store. Throws a user-facing
 * error if no provider/model is configured.
 */
export function preparePayload(payload, storage = localStorage) {
  const provider = payload.aiCmd || storage.getItem(ACTIVE_PROVIDER_KEY) || "";
  if (!provider) throw userFacingError("evaluate.noProviderSelected");
  const get = (key) => storage.getItem(providerKey(provider, key));
  const model = payload.aiModel || get("model");
  if (!model) throw userFacingError("evaluate.noModelSelected");
  const settings = resolveProviderSettings(provider, storage);
  const result = {
    ...payload,
    aiCmd: provider,
    aiModel: model,
    maxSubagents: settings.subagents,
    timeLimit: payload.timeLimit ?? settings.timeLimitS,
  };
  if (!settings.verify) result.verifyFindings = false;
  const apiBase = get("api-base");
  if (apiBase) result.apiBase = apiBase;
  // The Settings field pre-fills the provider id as its default; only a
  // real change is an override worth sending.
  const cmdPath = get("cmd-path");
  if (cmdPath && cmdPath !== provider) result.aiCmdPath = cmdPath;
  return result;
}
