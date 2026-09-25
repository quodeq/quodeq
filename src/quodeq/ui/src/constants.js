import { GRANULARITY } from './utils/granularity.js';
import { SECONDS_PER_MINUTE, MS_PER_SECOND } from './utils/time.js';

const UNDEFINED_TYPEOF = 'undefined'; // typeof sentinel for the event-dispatch helpers' "are we in a browser" guard

// Vite env vars are always strings, never coerced to boolean; every reader
// of a VITE_* boolean flag (VITE_USE_SSE_EVENTS) compares against this
// instead of the literal 'true'.
export const ENV_TRUE = 'true';

export const ISO_25010_URL = 'https://www.iso.org/';

// Upper bound of every dimension/principle/overall score axis: scores are
// always shown and compared on a 0-10 scale. Shared across the score charts,
// compare views, the grade-formula boundary editor and the map visualization
// so they all agree on where "full score" is.
export const SCORE_SCALE_MAX = 10;

// Fraction-to-percent multiplier, and the ceiling of any value already on
// the percent axis (a progress bar's aria-valuemax, a percent field's full
// value). Shared by every `* 100` percent conversion and percent-scale
// ceiling across the app so they all agree on what "100%" means. Not a
// general-purpose "100" default — a value on a different 0-100 domain scale
// (e.g. confidence) gets its own name next to that scale's other constants.
export const PERCENT = 100;

// Idle timeout for an SSE stream (the assistant chat and the eval job log):
// no frame for this long and the stream is treated as stalled and torn
// down. Shared by useAssistantStream and useJobLogStream so both time out
// identically instead of drifting apart if one is tuned and not the other.
export const STREAM_INACTIVITY_MS = SECONDS_PER_MINUTE * MS_PER_SECOND;

// Settings defaults & localStorage keys (shared by SettingsPage + useEvaluation).
// These client-side defaults can be overridden by server config (ai_providers.json).
export const DEFAULT_MAX_SUBAGENTS = 5;
export const DEFAULT_TIME_LIMIT_S = 600;
export const MIN_SUBAGENTS = 1;
export const MAX_SUBAGENTS = 10;
export const SUBAGENTS_STORAGE_KEY = 'cc-max-subagents';
export const TIME_LIMIT_STORAGE_KEY = 'cc-time-limit';

export const AI_CMD_STORAGE_KEY = 'cc-ai-cmd';
export const PER_DIMENSION_STORAGE_KEY = 'cc-per-dimension';

export const ACTIVE_PROVIDER_KEY = 'cc-active-provider';

export function providerKey(providerId, setting) {
  return `cc-${providerId}-${setting}`;
}

// Written under providerKey(id, PROVIDER_SETTING_KEY.API_KEY) instead of the raw credential once
// the backend confirms it stored one, so "configured" survives a reload
// without the key itself ever going back into localStorage. Lives here, next
// to providerKey, because both the settings hook that writes it and the
// evaluation payload builder that must refuse to forward it need it.
// Named without "key"/"secret"/"token": CodeQL's clear-text-storage rule
// classifies a value as sensitive from its identifier, so the old
// API_KEY_CONFIGURED_SENTINEL made every localStorage write reachable from
// this module read as a credential leak (4 high false positives, including
// on files that never touch it).
export const PROVIDER_CONFIGURED_MARKER = '•configured•';

// providerKey() setting-name suffixes shared across the provider-settings
// hook, its tabs, the legacy migration, the onboarding active-provider
// reader and the effective-settings resolver — one home so all of them read
// the same suffix. POOL_BUDGET is the legacy name TIME_LIMIT replaced, still
// read as a fallback.
export const PROVIDER_SETTING_KEY = Object.freeze({
  MODEL: 'model',
  MODEL_ANALYSIS: 'model-analysis',
  MODEL_FAST: 'model-fast',
  MODEL_BALANCED: 'model-balanced',
  MODEL_THOROUGH: 'model-thorough',
  SUBAGENTS: 'subagents',
  TIME_LIMIT: 'time-limit',
  PER_DIMENSION: 'per-dimension',
  VERIFY: 'verify',
  API_KEY: 'api-key',
  API_BASE: 'api-base',
  CMD_PATH: 'cmd-path',
  POOL_BUDGET: 'pool-budget',
});

// Fired (same-tab) whenever any provider setting is written — the analysis
// active-provider or a per-provider model. The assistant gate listens for it
// so that in Default mode (which mirrors the analysis provider/model) the
// displayed model updates live when the user changes it in Settings. The
// native 'storage' event only fires cross-tab, so we need this in-tab signal.
export const PROVIDER_SETTINGS_CHANGED_EVENT = 'cc-provider-settings-changed';

export function notifyProviderSettingsChanged() {
  if (typeof window !== UNDEFINED_TYPEOF) {
    window.dispatchEvent(new Event(PROVIDER_SETTINGS_CHANGED_EVENT));
  }
}

// Fired (same-tab) whenever the set of standards or their per-project
// visibility changes. Screens that hold the merged dimension list (the
// Evaluate picker) listen so a starred, created, imported or duplicated
// standard shows up without a page reload. `detail.reason` says how much
// moved: VISIBILITY (refilter the cached list) or LIST (refetch it).
export const STANDARDS_CHANGED_EVENT = 'quodeq:standards-changed';
export const STANDARDS_CHANGED_REASON = Object.freeze({ VISIBILITY: 'visibility', LIST: 'list' });

export function notifyStandardsChanged(reason) {
  if (typeof window !== UNDEFINED_TYPEOF) {
    window.dispatchEvent(new CustomEvent(STANDARDS_CHANGED_EVENT, { detail: { reason } }));
  }
}

// Last directory a repo was cloned into: offered as the default clone
// target by onboarding and by the dashboard's complete-setup card.
export const LAST_CLONE_ROOT_STORAGE_KEY = 'quodeq.lastCloneRoot';

export const VISIBLE_STANDARDS_STORAGE_KEY = 'quodeq-visible-standards';
export const DEFAULT_VISIBLE_STANDARDS = [
  'security', 'reliability', 'maintainability', 'performance', 'usability', 'flexibility',
];

export const SCORE_HISTORY_GRANULARITY_STORAGE_KEY = 'quodeq-score-history-granularity';
export const DEFAULT_SCORE_HISTORY_GRANULARITY = GRANULARITY.DAY;

// Fired (same-tab) by the assistant's ActionPreviewCard after a successful
// apply, with { actionType, scores, delta } as detail. App-level effects and
// the verified-findings context listen so caches converge like a manual dismiss.
export const ASSISTANT_ACTION_APPLIED_EVENT = 'quodeq:assistant-action-applied';

export function notifyAssistantActionApplied(detail) {
  if (typeof window !== UNDEFINED_TYPEOF) {
    window.dispatchEvent(new CustomEvent(ASSISTANT_ACTION_APPLIED_EVENT, { detail }));
  }
}

// Fired (same-tab) after Settings kills every terminal session server-side,
// so TerminalPane can reconcile its stale views. See TerminalSection.jsx
// (dispatcher) and TerminalPane.jsx (listener).
export const TERMINAL_RESTART_EVENT = 'quodeq:terminal-restart';

// <html> attribute carrying the applied theme; every theme CSS selector keys on it.
export const DATA_THEME_ATTR = 'data-theme';
// OS dark-mode media query, consulted whenever the theme mode is 'system'.
export const PREFERS_DARK_QUERY = '(prefers-color-scheme: dark)';
// Mobile layout breakpoint. Mirrors the 900px @media rules in terminal.css,
// assistant.css, standards.css, help.css and base.css; change them together.
const MOBILE_BREAKPOINT_PX = 900;
export const MOBILE_BREAKPOINT_QUERY = `(max-width: ${MOBILE_BREAKPOINT_PX}px)`;
// Third-party contract: pywebview dispatches this on window once its JS
// bridge is injected. Never rename.
export const PYWEBVIEW_READY_EVENT = 'pywebviewready';

// HTTP status codes the UI branches on by name (a 409 collision, a 404
// gone-missing). Not a full status enum, only the codes callers compare
// against res.status / err.status.
export const HTTP_STATUS = Object.freeze({ CONFLICT: 409, NOT_FOUND: 404 });

// URL.protocol values (trailing colon included, per the URL spec) the UI
// branches on: openExternal's web-scheme allowlist and terminalSocketUrl's
// http(s) -> ws(s) upgrade.
export const URL_PROTOCOL = Object.freeze({ HTTP: 'http:', HTTPS: 'https:' });

// Run-id sentinel meaning "the most recently completed run" -- the
// default/fallback wherever a specific run id has not been selected
// (query keys, the run navigator, route params). Never a real run id.
export const LATEST_RUN_ID = 'latest';

// Fetch/DOMException .name values from AbortSignal.timeout(): api/projects.js
// (registerProject) and api/sharedPublish.js (pullSharedProject) both treat
// either as "the request timed out or was aborted", not a real server error.
export const FETCH_ERROR_NAME = Object.freeze({ TIMEOUT: 'TimeoutError', ABORT: 'AbortError' });

// Promise.allSettled()'s result.status for a resolved promise: the health
// port scan (hooks/useServerHealth.js) and onboarding's provider probes.
export const SETTLED_FULFILLED = 'fulfilled';
