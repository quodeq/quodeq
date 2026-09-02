/**
 * useEvaluation helpers: poll-interval policy and start-payload prep.
 *
 * Split out of useEvaluation.js (see that file's header for the hook's
 * overall data-flow doc). Kept logic-identical to the pre-split version.
 */
import { ACTIVE_PROVIDER_KEY, providerKey } from "../../../constants.js";
import { resolveProviderSettings } from "../../../utils/effectiveProviderSettings.js";
import { t } from "../../../strings/index.js";

export const SSE_ENABLED = import.meta.env?.VITE_USE_SSE_EVENTS === "true";
const DIM_POLL_MS = 2000;

/**
 * Poll interval for the live findings query. Exported for tests.
 *
 * Polling must stop once the job is terminal: without the gate a finished
 * run kept re-fetching every full evaluation/<dim>.json payload every 2s
 * for as long as the Evaluate card stayed mounted.
 */
export function findingsRefetchInterval(job, sseEnabled = SSE_ENABLED) {
  if (sseEnabled) return false;
  if (job?.status && job.status !== "running") return false;
  return DIM_POLL_MS;
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
 * and the Evaluate header display. Throws a user-facing error if no
 * provider/model is configured.
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
  if (settings.perDimension) result.perDimension = true;
  if (!settings.verify) result.verifyFindings = false;
  const apiKey = get("api-key");
  if (apiKey) result.apiKey = apiKey;
  const apiBase = get("api-base");
  if (apiBase) result.apiBase = apiBase;
  // The Settings field pre-fills the provider id as its default; only a
  // real change is an override worth sending.
  const cmdPath = get("cmd-path");
  if (cmdPath && cmdPath !== provider) result.aiCmdPath = cmdPath;
  return result;
}
